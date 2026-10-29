from abc import ABC, abstractmethod
from typing import Dict, Any

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.textutil import jaccard, stem_set


class PairwiseEvaluationTrace:
    def __init__(self, is_duplicate: bool, score: float, reason: str):
        self.is_duplicate = is_duplicate
        self.score = score
        self.reason = reason


class BasePairwiseEvaluator(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def evaluate_pair(self, evidence_a: CandidateEvidence, evidence_b: CandidateEvidence, context: Dict[str, Any] = None) -> PairwiseEvaluationTrace:
        pass


class TokenJaccardPairwiseEvaluator(BasePairwiseEvaluator):
    """
    Deterministic near-duplicate check: two chunks whose word sets overlap
    almost completely (default 90%) say the same thing. No model needed.
    """

    def __init__(self, threshold: float = 0.9):
        self.threshold = threshold

    @property
    def name(self) -> str:
        return "token_jaccard_pairwise"

    def evaluate_pair(self, evidence_a, evidence_b, context=None) -> PairwiseEvaluationTrace:
        score = jaccard(stem_set(evidence_a.content), stem_set(evidence_b.content))
        return PairwiseEvaluationTrace(score >= self.threshold, score, f"word overlap {score:.2f}")


class CrossEncoderPairwiseEvaluator(BasePairwiseEvaluator):
    """Optional model-based near-duplicate check. Needs sentence-transformers."""

    def __init__(self, model_name: str = "cross-encoder/stsb-distilroberta-base", threshold: float = 0.85):
        self.model_name = model_name
        self.threshold = threshold
        self._model = None

    @property
    def name(self) -> str:
        return "cross_encoder_pairwise"

    def evaluate_pair(self, evidence_a, evidence_b, context=None) -> PairwiseEvaluationTrace:
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        score = float(self._model.predict([(evidence_a.content[:1500], evidence_b.content[:1500])])[0])
        return PairwiseEvaluationTrace(score >= self.threshold, score, f"cross-encoder similarity {score:.2f}")