from abc import ABC, abstractmethod
from typing import Any, Dict

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.evidence.models import EvidenceEvaluationTrace

class BaseEvaluator(ABC):
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, candidate: CandidateEvidence, context: Dict[str, Any]) -> EvidenceEvaluationTrace:
        """
        Evaluate a candidate and return a trace containing the signal.
        The framework must NEVER directly return EvidenceState.
        """
        pass
