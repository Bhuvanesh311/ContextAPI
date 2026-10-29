
import re
from typing import List, Mapping, Any

from sqlalchemy.orm import Session

from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.scope_guard import require_version_scope
from app.knowledge.uploads.models import DocumentChunk


class StructuredSearchRequest:
    def __init__(self, query_text: str, top_k: int, filters: Mapping[str, Any]):
        self.query_text = query_text
        self.top_k = top_k
        self.filters = filters


def _extract_phrases(text: str) -> List[str]:
    """
    Return phrases inside straight or curly double-quotes.
    Curly quotes (“ / ”) are normalised to straight quotes first
    so a single regex handles both.
    """
    normalised = text.replace("“", '"').replace("”", '"')
    return re.findall(r'"([^"]+)"', normalised)


def _ilike_escape(phrase: str) -> str:
    """Escape LIKE special characters so the phrase is matched literally."""
    return phrase.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")


class PostgresStructuredStoreAdapter:
    """
    Exact-phrase retrieval against DocumentChunk.content.

    Only fires when the query contains at least one quoted phrase (straight or
    curly quotes).  Without a phrase the step returns [] so the caller falls
    back to hybrid search instead of returning random in-scope chunks.

    Scope filter (document_version_id "$in") is applied first so only
    documents the caller is authorised to see are searched.
    """

    def __init__(self, session: Session):
        self.session = session

    def search(self, request: StructuredSearchRequest, step_id: str) -> List[RawRetrievalResult]:
        version_ids = require_version_scope(request.filters)
        phrases = _extract_phrases(request.query_text)

        # No quoted phrase → nothing to do; let caller fall back to hybrid search.
        if not phrases:
            return []

        query = self.session.query(DocumentChunk.chunk_id).filter(
            DocumentChunk.document_version_id.in_(version_ids)
        )

        for phrase in phrases:
            escaped = _ilike_escape(phrase)
            query = query.filter(
                DocumentChunk.content.ilike(f"%{escaped}%", escape="\\")
            )

        query = query.limit(request.top_k)

        raw_hits = []
        for row in query.all():
            chunk_id = row[0]
            raw_hits.append(
                RawRetrievalResult(
                    step_id=step_id,
                    vector_id=f"lexical_{chunk_id}",
                    score=1.0,
                    metadata_hits={"chunk_id": chunk_id, "match_type": "exact_phrase"},
                )
            )

        return raw_hits
