import time
from typing import Dict, Any

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.evidence.evaluators.base import BaseEvaluator
from app.retrieval.evidence.models import EvidenceEvaluationTrace

class DeterministicValidator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "deterministic_validator"
        
    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        start = time.time()
        
        # Check required fields
        if not candidate.evidence_id or not candidate.content:
            return EvidenceEvaluationTrace(
                evaluator_name=self.name,
                signal_type="validity",
                signal_value=False,
                reason="Missing evidence_id or content",
                latency_ms=int((time.time() - start) * 1000)
            )
            
        if not candidate.provenance or not getattr(candidate.provenance, 'document_id', None):
            return EvidenceEvaluationTrace(
                evaluator_name=self.name,
                signal_type="validity",
                signal_value=False,
                reason="Missing provenance or document_id",
                latency_ms=int((time.time() - start) * 1000)
            )
            
        # Scope validation
        required_scope = context.get("required_scope", {})
        candidate_metadata = candidate.retrieval_metadata or {}
        
        for k, v in required_scope.items():
            if candidate_metadata.get(k) != v:
                return EvidenceEvaluationTrace(
                    evaluator_name=self.name,
                    signal_type="validity",
                    signal_value=False,
                    reason=f"Scope mismatch for {k}: expected {v}, got {candidate_metadata.get(k)}",
                    latency_ms=int((time.time() - start) * 1000)
                )
                
        return EvidenceEvaluationTrace(
            evaluator_name=self.name,
            signal_type="validity",
            signal_value=True,
            reason="Passed deterministic validation",
            latency_ms=int((time.time() - start) * 1000)
        )
