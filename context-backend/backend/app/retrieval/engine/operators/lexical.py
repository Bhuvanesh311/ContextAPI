
from typing import Mapping, Any, List
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.planning.schemas import RetrievalStep
from app.retrieval.engine.schemas import RawRetrievalResult
from app.retrieval.engine.adapters.lexical_store import (
    LexicalStoreAdapter, LexicalSearchRequest
)

class LexicalOperator(BaseOperator):
    
    def __init__(self, lexical_adapter: LexicalStoreAdapter):
        self.lexical_adapter = lexical_adapter
    
    @property
    def capability_id(self) -> str:
        return "cap_lexical"
        
    def execute(self, step: RetrievalStep, context_data: Mapping[str, Any]) -> List[RawRetrievalResult]:
        filters = dict(step.step_scope)
        
        search_req = LexicalSearchRequest(
            query_text=step.query_binding.query_text,
            top_k=context_data.get("top_k", 10),
            filters=filters
        )
        
        raw_results = self.lexical_adapter.search(search_req, step.step_id)
        return raw_results
