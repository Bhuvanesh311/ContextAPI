from typing import Dict, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import QueryComplexity, QueryIntent
from app.retrieval.sufficiency.enums import SignalName
from app.retrieval.sufficiency.exceptions import SufficiencyConfigError


def _default_evidence_targets() -> Dict[QueryComplexity, int]:
    return {
        QueryComplexity.LOW: 2,
        QueryComplexity.MEDIUM: 3,
        QueryComplexity.HIGH: 4,
        QueryComplexity.VERY_HIGH: 5,
    }


def _default_weights() -> Dict[str, float]:
    return {
        SignalName.TERM_COVERAGE.value: 0.35,
        SignalName.SUBQUERY_COVERAGE.value: 0.15,
        SignalName.EVIDENCE_QUANTITY.value: 0.15,
        SignalName.SOURCE_DIVERSITY.value: 0.10,
        SignalName.CONTENT_ADEQUACY.value: 0.10,
        SignalName.RETRIEVAL_CONSENSUS.value: 0.10,
        SignalName.EXECUTION_HEALTH.value: 0.05,
        SignalName.EVIDENCE_CONFLICT.value: 0.05,
    }


class SufficiencyConfig(BaseModel):
    """
    Every threshold L07 uses lives here, so tuning never means editing logic.

    Scores are compared as 0..1 ratios. A signal "passes" when its value
    reaches its target. Targets that depend on the request (complexity,
    intent, number of searchable documents) come from the helper methods.
    """
    model_config = ConfigDict(frozen=True)

    # ---- loop limits ------------------------------------------------------
    # Total retrieval rounds, including the first one. The plan's own
    # execution_limits.max_rounds can only make this smaller, never larger.
    max_rounds: int = 3
    # Wall-clock budget for the whole loop (all rounds together).
    max_total_latency_ms: int = 45000
    # Do not start another round with less time than this left.
    min_round_budget_ms: int = 2000
    # Stop after this many escalation rounds in a row found nothing new.
    max_consecutive_no_progress: int = 2
    top_k_growth_factor: int = 2
    max_top_k: int = 30
    # True: L07 may return more than the requested top_k when it had to
    # dig deeper. False: never return more than the requested top_k.
    allow_top_k_growth: bool = True

    # ---- verdict thresholds ----------------------------------------------
    sufficient_score: float = 0.80
    partial_score: float = 0.50
    # Below this term coverage the evidence is not about the question at all.
    coverage_floor: float = 0.34

    # ---- signal targets ---------------------------------------------------
    min_term_coverage: float = 0.60
    min_term_coverage_complex: float = 0.50   # HIGH / VERY_HIGH queries
    # A sub-question counts as covered when this share of its terms is found.
    min_subquery_term_coverage: float = 0.50
    min_total_chars: int = 300
    min_consensus: float = 0.30
    consensus_top_n: int = 3
    evidence_target_by_complexity: Mapping[QueryComplexity, int] = Field(
        default_factory=_default_evidence_targets
    )
    multi_source_intents: Tuple[QueryIntent, ...] = (
        QueryIntent.COMPARISON,
        QueryIntent.RELATIONSHIP,
        QueryIntent.MULTI_STEP,
        QueryIntent.INVESTIGATION,
    )
    min_sources_for_multi_source_intents: int = 2

    # ---- score weights (re-normalised over the signals that apply) -------
    weights: Mapping[str, float] = Field(default_factory=_default_weights)

    # ---- request status ---------------------------------------------------
    # False (default): a request that ends with gaps is still COMPLETED and
    # the gaps are reported in `sufficiency`. True: it ends as PARTIAL.
    partial_status_on_gaps: bool = False

    # ---- helpers ----------------------------------------------------------
    def evidence_target(self, complexity: QueryComplexity, top_k: int) -> int:
        wanted = self.evidence_target_by_complexity.get(complexity, 2)
        return max(1, min(wanted, top_k))

    def coverage_target(self, complexity: QueryComplexity) -> float:
        if complexity in (QueryComplexity.HIGH, QueryComplexity.VERY_HIGH):
            return self.min_term_coverage_complex
        return self.min_term_coverage

    def source_target(self, intent: QueryIntent, available_documents: Optional[int]) -> int:
        if intent not in self.multi_source_intents:
            return 1
        target = self.min_sources_for_multi_source_intents
        if available_documents is not None:
            # Cannot ask for more sources than the project has.
            target = min(target, max(1, available_documents))
        return target

    def validate_config(self) -> None:
        if self.max_rounds < 1:
            raise SufficiencyConfigError("max_rounds must be >= 1")
        if self.max_total_latency_ms <= 0:
            raise SufficiencyConfigError("max_total_latency_ms must be > 0")
        if not (0.0 <= self.partial_score <= self.sufficient_score <= 1.0):
            raise SufficiencyConfigError("need 0 <= partial_score <= sufficient_score <= 1")
        if not (0.0 <= self.coverage_floor <= 1.0):
            raise SufficiencyConfigError("coverage_floor must be within 0..1")
        if self.top_k_growth_factor < 2:
            raise SufficiencyConfigError("top_k_growth_factor must be >= 2")
        if self.max_top_k < 1:
            raise SufficiencyConfigError("max_top_k must be >= 1")
        if any(w < 0 for w in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise SufficiencyConfigError("weights must be non-negative and not all zero")
        unknown = set(self.weights) - {s.value for s in SignalName}
        if unknown:
            raise SufficiencyConfigError(f"unknown signal names in weights: {sorted(unknown)}")
