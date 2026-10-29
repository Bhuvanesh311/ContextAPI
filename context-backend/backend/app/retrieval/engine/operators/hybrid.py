import concurrent.futures as cf
from collections import defaultdict
from typing import Any, Dict, List, Mapping, Sequence

from sqlalchemy.orm import Session

from app.knowledge.uploads.models import ChunkEmbedding
from app.retrieval.engine.exceptions import ScopeViolationError
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.planning.schemas import RetrievalStep

RRF_K = 60

# Vector search runs here while lexical search runs on the caller's thread.
# Only the semantic side may go to another thread: lexical uses the request's
# SQLAlchemy Session, which is not thread-safe.
_PARALLEL_POOL = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="hybrid-semantic")


def rrf_fuse(ranked_lists: Sequence[Sequence[str]], k: int = RRF_K) -> List[tuple]:
    """
    Reciprocal Rank Fusion over ranked lists of chunk ids.

    score(chunk) = sum over lists of 1 / (k + rank), rank starting at 1.
    A chunk found by both retrievers therefore outranks one found by one.
    Ties keep first-seen order (semantic list goes first).
    """
    scores: Dict[str, float] = defaultdict(float)
    for ids in ranked_lists:
        seen = set()
        rank = 0
        for chunk_id in ids:
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            rank += 1
            scores[chunk_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda item: -item[1])


class HybridOperator(BaseOperator):
    """Semantic (Chroma) + lexical (Postgres full-text) fused with RRF."""

    def __init__(self, semantic_operator: BaseOperator, lexical_operator: BaseOperator, session: Session):
        self.semantic_operator = semantic_operator
        self.lexical_operator = lexical_operator
        self.session = session

    @property
    def capability_id(self) -> str:
        return "cap_hybrid"

    def execute(self, step: RetrievalStep, context_data: Mapping[str, Any]) -> List[RawRetrievalResult]:
        top_k = context_data.get("top_k", 10)
        semantic: List[RawRetrievalResult] = []
        lexical: List[RawRetrievalResult] = []
        errors: List[Exception] = []

        semantic_future = _PARALLEL_POOL.submit(self.semantic_operator.execute, step, context_data)

        try:
            lexical = self.lexical_operator.execute(step, context_data)
        except ScopeViolationError:
            semantic_future.cancel()
            raise
        except Exception as exc:
            errors.append(exc)

        try:
            # The semantic side enforces its own per-call timeouts.
            semantic = semantic_future.result()
        except ScopeViolationError:
            raise
        except Exception as exc:
            errors.append(exc)

        # One side failing is fine (the other still answers). Both failing
        # is a real failure, so let the executor record it.
        if len(errors) == 2:
            raise errors[0]

        return self._fuse(step.step_id, semantic, lexical, top_k)

    def _semantic_chunk_map(self, semantic: List[RawRetrievalResult]) -> Dict[str, str]:
        """
        Chroma vector ids are sha256 hashes and Chroma metadata has no
        chunk_id, so map vector_id -> chunk_id through chunk_embeddings.
        """
        vector_ids = [r.vector_id for r in semantic if r.vector_id]
        if not vector_ids:
            return {}
        rows = (
            self.session.query(ChunkEmbedding.vector_id, ChunkEmbedding.chunk_id)
            .filter(ChunkEmbedding.vector_id.in_(vector_ids))
            .all()
        )
        return {vector_id: chunk_id for vector_id, chunk_id in rows}

    def _fuse(
        self,
        step_id: str,
        semantic: List[RawRetrievalResult],
        lexical: List[RawRetrievalResult],
        top_k: int,
    ) -> List[RawRetrievalResult]:
        sem_map = self._semantic_chunk_map(semantic)

        sem_ids: List[str] = []
        best: Dict[str, RawRetrievalResult] = {}
        found_by: Dict[str, set] = defaultdict(set)

        for res in semantic:
            chunk_id = sem_map.get(res.vector_id)
            if not chunk_id:
                continue  # cannot be resolved to a chunk later either
            sem_ids.append(chunk_id)
            best.setdefault(chunk_id, res)  # semantic id resolves via ChunkEmbedding
            found_by[chunk_id].add("semantic")

        lex_ids: List[str] = []
        for res in lexical:
            chunk_id = res.metadata_hits.get("chunk_id")
            if not chunk_id:
                continue
            lex_ids.append(chunk_id)
            best.setdefault(chunk_id, res)
            found_by[chunk_id].add("lexical")

        fused = rrf_fuse([sem_ids, lex_ids])[:top_k]

        results: List[RawRetrievalResult] = []
        for chunk_id, score in fused:
            original = best[chunk_id]
            metadata = dict(original.metadata_hits)
            metadata["chunk_id"] = chunk_id
            metadata["matched_by"] = "+".join(sorted(found_by[chunk_id]))
            results.append(
                RawRetrievalResult(
                    step_id=step_id,
                    vector_id=original.vector_id,
                    score=score,
                    metadata_hits=metadata,
                )
            )
        return results