import re
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Dict, List

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError, DBAPIError
from sqlalchemy.orm import Session

from app.knowledge.uploads.models import DocumentChunk
from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.scope_guard import require_version_scope


def _thaw(value):
    """Frozen planner structures (FrozenDict / tuple) -> plain dict / list."""
    if isinstance(value, Mapping):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_thaw(v) for v in value]
    return value


def build_or_tsquery(text: str) -> str:
    """
    Turn free text into a safe Postgres tsquery string joined with OR.

    "What is ContextAPI?"  ->  "what | is | contextapi"

    - Only letters/digits are kept, so characters such as ? ' : & ( ) can
      never cause a tsquery syntax error.
    - OR (not AND): natural-language questions contain filler words, and
      requiring every word to match would return nothing. ts_rank_cd still
      ranks chunks that match more terms higher.
    - Stopwords ("what", "is") are dropped by the 'english' config.
    """
    terms = re.findall(r"[^\W_]+", text or "", flags=re.UNICODE)
    seen = set()
    unique: List[str] = []
    for term in terms:
        low = term.lower()
        if low not in seen:
            seen.add(low)
            unique.append(low)
    return " | ".join(unique)


class LexicalSearchRequest(BaseModel):
    query_text: str
    top_k: int
    filters: Dict[str, Any]


class LexicalStoreAdapter(ABC):
    @abstractmethod
    def search(self, request: LexicalSearchRequest, step_id: str) -> List[RawRetrievalResult]:
        pass


class PostgresLexicalStoreAdapter(LexicalStoreAdapter):
    def __init__(self, session: Session):
        self.session = session

    def _apply_filters(self, query, filters: Dict[str, Any]):
        """
        Translate the step scope into SQL.

        The scope arrives in ChromaDB style, e.g.
            {"document_version_id": {"$in": ["DOCV000001", ...]}}
        Keys that are real document_chunks columns become column filters;
        anything else is looked up inside chunk_metadata.
        """
        columns = DocumentChunk.__table__.columns
        for key, value in _thaw(dict(filters or {})).items():
            if key in columns:
                column = getattr(DocumentChunk, key)
                if isinstance(value, dict):
                    if set(value) == {"$in"}:
                        query = query.filter(column.in_(list(value["$in"])))
                    elif set(value) == {"$eq"}:
                        query = query.filter(column == value["$eq"])
                    else:
                        raise ValueError(
                            f"Unsupported filter operator for '{key}': {sorted(value)}"
                        )
                else:
                    query = query.filter(column == value)
            else:
                query = query.filter(
                    DocumentChunk.chunk_metadata.op("->>")(key) == str(value)
                )
        return query

    def search(self, request: LexicalSearchRequest, step_id: str) -> List[RawRetrievalResult]:
        require_version_scope(_thaw(dict(request.filters or {})))
        ts_query_str = build_or_tsquery(request.query_text)
        if not ts_query_str:
            return []

        tsquery = func.to_tsquery("english", ts_query_str)
        rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery).label("rank")

        query = self.session.query(DocumentChunk.chunk_id, rank).filter(
            DocumentChunk.search_vector.op("@@")(tsquery)
        )
        query = self._apply_filters(query, request.filters)
        query = query.order_by(rank.desc()).limit(request.top_k)

        # SAVEPOINT: if this query fails, only it is rolled back. The outer
        # request transaction (and the semantic half of a hybrid search)
        # stays usable.
        # ProgrammingError/DBAPIError: to_tsquery raises "text-search query
        # doesn't contain lexemes" when every token in the query is a
        # PostgreSQL stop-word (e.g. "what is it?"). Return empty gracefully
        # so hybrid mode falls back to semantic results.
        try:
            with self.session.begin_nested():
                rows = query.all()
        except (ProgrammingError, DBAPIError):
            return []

        return [
            RawRetrievalResult(
                step_id=step_id,
                # Resolved straight to document_chunks (no ChunkEmbedding row),
                # see PostgresContentResolver.
                vector_id=f"lexical_{chunk_id}",
                score=float(chunk_rank or 0.0),
                metadata_hits={"chunk_id": chunk_id},
            )
            for chunk_id, chunk_rank in rows
        ]