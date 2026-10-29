
from functools import lru_cache
from typing import Mapping, Any, List
from app.core.config import settings
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.engine.timeouts import budgeted_timeout, call_with_timeout
from app.retrieval.planning.schemas import RetrievalStep
from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.adapters.embedding import (
    EmbeddingAdapter, QueryEmbeddingRequest
)
from app.retrieval.engine.adapters.vector_store import (
    VectorStoreAdapter, VectorSearchRequest
)

class SemanticOperator(BaseOperator):

    def __init__(self, embedding_adapter: EmbeddingAdapter, vector_adapter: VectorStoreAdapter):
        self.embedding_adapter = embedding_adapter
        self.vector_adapter = vector_adapter
        # The same query text is searched by several steps and L07 rounds;
        # embed it once. Bounded, thread-safe, shared across requests.
        self._embed = lru_cache(maxsize=1024)(self._embed_uncached)

    def _embed_uncached(self, query_text: str) -> tuple:
        res = self.embedding_adapter.embed_query(QueryEmbeddingRequest(query_text=query_text))
        return tuple(res.embedding)

    @property
    def capability_id(self) -> str:
        return "cap_semantic"

    def execute(self, step: RetrievalStep, context_data: Mapping[str, Any]) -> List[RawRetrievalResult]:
        # Each call is capped by min(its setting, time left in the request).
        deadline = context_data.get("deadline")

        embedding = call_with_timeout(
            self._embed,
            budgeted_timeout(settings.RETRIEVAL_EMBED_TIMEOUT_SECONDS, deadline),
            step.query_binding.query_text,
        )

        # Merge step_scope into filters
        filters = dict(step.step_scope)

        # Search Vector Store
        search_req = VectorSearchRequest(
            embedding=list(embedding),
            top_k=context_data.get("top_k", 10),
            filters=filters
        )

        return call_with_timeout(
            self.vector_adapter.search,
            budgeted_timeout(settings.RETRIEVAL_VECTOR_TIMEOUT_SECONDS, deadline),
            search_req,
            step.step_id,
        )
