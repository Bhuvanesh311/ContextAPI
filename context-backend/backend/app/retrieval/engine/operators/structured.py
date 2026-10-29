
from typing import Mapping, Any, List
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.planning.schemas import RetrievalStep
from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.adapters.structured_store import (
    PostgresStructuredStoreAdapter, StructuredSearchRequest
)

class StructuredOperator(BaseOperator):
    
    def __init__(self, structured_adapter: PostgresStructuredStoreAdapter):
        self.structured_adapter = structured_adapter
    
    @property
    def capability_id(self) -> str:
        return "cap_structured"
        
    def execute(self, step: RetrievalStep, context_data: Mapping[str, Any]) -> List[RawRetrievalResult]:
        filters = dict(step.step_scope)
        
        search_req = StructuredSearchRequest(
            query_text=step.query_binding.query_text,
            top_k=context_data.get("top_k", 10),
            filters=filters
        )
        
        raw_results = self.structured_adapter.search(search_req, step.step_id)
        return raw_results