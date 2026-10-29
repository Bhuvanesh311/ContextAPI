from typing import List, Optional, Tuple

from app.retrieval.engine.schemas import CandidateEvidence
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import EvidenceEvaluationTrace


class EvidencePolicy:
    """
    Turns the evaluator traces of one candidate into an EvidenceState.

    Order matters; the first rule that fires wins:
      1. mandatory deterministic validation fails        -> INVALID
      2. outside the L02 scope (scope defense)           -> INVALID
      3. provenance incomplete                           -> INVALID
      4. unusable content                                -> REJECTED
      5. document inactive or version superseded         -> REJECTED
         older than max_age_days (if set)                -> UNCERTAIN
      6. raw score below min_similarity_threshold (if set; off by default,
         raw scores are not calibrated)                  -> REJECTED
      7. no query-term overlap AND not found by semantic search -> REJECTED
      8. optional model evaluator signals                -> REJECTED / UNCERTAIN
      9. otherwise                                       -> ACCEPTED
    """

    def __init__(
        self,
        min_similarity_threshold: Optional[float] = None,
        min_relevance: float = 0.15,
        max_age_days: Optional[int] = None,
    ):
        self.min_similarity_threshold = min_similarity_threshold
        self.min_relevance = min_relevance
        self.max_age_days = max_age_days

    @staticmethod
    def _trace(traces: List[EvidenceEvaluationTrace], name: str) -> Optional[EvidenceEvaluationTrace]:
        return next((t for t in traces if t.evaluator_name == name), None)

    def determine_state(self, candidate: CandidateEvidence, traces: List[EvidenceEvaluationTrace]) -> Tuple[EvidenceState, str]:
        val = self._trace(traces, "deterministic_validator")
        if not val or val.signal_value is not True:
            return EvidenceState.INVALID, (val.reason if val else "Missing deterministic validation")

        scope = self._trace(traces, "scope_defense")
        if scope and scope.signal_value is False:
            return EvidenceState.INVALID, scope.reason

        prov = self._trace(traces, "provenance_validator")
        if prov and prov.signal_value is False:
            return EvidenceState.INVALID, prov.reason

        quality = self._trace(traces, "quality_evaluator")
        if quality and quality.signal_value is False:
            return EvidenceState.REJECTED, quality.reason

        auth = self._trace(traces, "authority_freshness")
        if auth and isinstance(auth.signal_value, dict):
            status = auth.signal_value.get("status")
            if status in ("inactive", "superseded"):
                return EvidenceState.REJECTED, f"Document is {status}"
            age = auth.signal_value.get("age_days")
            if self.max_age_days is not None and age is not None and age > self.max_age_days:
                return EvidenceState.UNCERTAIN, f"Document last updated {age} days ago"

        sim = self._trace(traces, "similarity_evaluator")
        if sim and self.min_similarity_threshold is not None:
            score = sim.signal_value
            if score < self.min_similarity_threshold:
                return EvidenceState.REJECTED, f"Score {score:.3f} below threshold {self.min_similarity_threshold}"

        rel = self._trace(traces, "relevance_evaluator")
        if rel and isinstance(rel.signal_value, dict):
            coverage = rel.signal_value.get("coverage", 1.0)
            if coverage < self.min_relevance and not rel.signal_value.get("semantic", True):
                return EvidenceState.REJECTED, "No question terms in the evidence and not found by semantic search"

        model_trace = self._trace(traces, "model_evaluator")
        if model_trace:
            sig = model_trace.signal_value
            if not isinstance(sig, dict) or "relevance" not in sig:
                return EvidenceState.UNCERTAIN, "Model evaluation returned malformed signal"
            rel_level = sig.get("relevance")
            if rel_level == "low":
                return EvidenceState.REJECTED, "Model evaluated as low relevance"
            if rel_level == "medium":
                return EvidenceState.UNCERTAIN, "Model evaluated as medium relevance"

        return EvidenceState.ACCEPTED, "Passed all policy constraints"