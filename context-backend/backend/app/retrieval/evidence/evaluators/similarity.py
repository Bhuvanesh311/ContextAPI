import time
from typing import Dict, Any

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.evidence.evaluators.base import BaseEvaluator
from app.retrieval.evidence.models import EvidenceEvaluationTrace

class SimilarityEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "similarity_evaluator"
        
    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        
        score = candidate.score
        
        return EvidenceEvaluationTrace(
            evaluator_name=self.name,
            signal_type="similarity_score",
            signal_value=score,
            reason=f"Retrieved with score {score:.3f}",
            latency_ms=int((time.time() - start) * 1000)
        )
