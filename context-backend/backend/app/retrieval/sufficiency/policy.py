from typing import Dict, List, Sequence, Tuple

from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.enums import (
    GapSeverity,
    GapType,
    SignalName,
    SufficiencyVerdict,
)
from app.retrieval.sufficiency.evaluators.base import AssessmentInput
from app.retrieval.sufficiency.models import (
    SufficiencyAssessment,
    SufficiencyGap,
    SufficiencySignal,
)

# Which gap a failed signal turns into, and how serious it is.
_SIGNAL_TO_GAP: Dict[SignalName, Tuple[GapType, GapSeverity]] = {
    SignalName.TERM_COVERAGE: (GapType.LOW_TERM_COVERAGE, GapSeverity.HARD),
    SignalName.SUBQUERY_COVERAGE: (GapType.SUBQUERY_UNCOVERED, GapSeverity.HARD),
    SignalName.SOURCE_DIVERSITY: (GapType.LOW_SOURCE_DIVERSITY, GapSeverity.HARD),
    SignalName.EVIDENCE_QUANTITY: (GapType.TOO_FEW_EVIDENCE, GapSeverity.SOFT),
    SignalName.CONTENT_ADEQUACY: (GapType.LOW_CONTENT, GapSeverity.SOFT),
    SignalName.RETRIEVAL_CONSENSUS: (GapType.WEAK_AGREEMENT, GapSeverity.SOFT),
    SignalName.EXECUTION_HEALTH: (GapType.EXECUTION_DEGRADED, GapSeverity.SOFT),
    SignalName.EVIDENCE_CONFLICT: (GapType.CONFLICT_UNRESOLVED, GapSeverity.SOFT),
}

_EPS = 1e-9


class SufficiencyPolicy:
    """
    Turns signals into gaps, a 0..1 score and a verdict.
    All the judging happens here, evaluators only measure.
    """

    def __init__(self, config: SufficiencyConfig):
        self.config = config

    def assess(
        self,
        signals: Sequence[SufficiencySignal],
        inp: AssessmentInput,
    ) -> SufficiencyAssessment:
        by_name = {s.signal_name: s for s in signals}
        accepted_count = len(inp.accepted)

        # ---- nothing usable was found ---------------------------------
        if accepted_count == 0:
            gaps: List[SufficiencyGap] = [
                SufficiencyGap(
                    gap_type=GapType.NO_EVIDENCE,
                    severity=GapSeverity.HARD,
                    message="No accepted evidence for this query",
                )
            ]
            health = by_name.get(SignalName.EXECUTION_HEALTH)
            if health and health.applicable and health.value + _EPS < health.target:
                gaps.append(self._gap_from_signal(health))
            return SufficiencyAssessment(
                round_index=inp.round_index,
                verdict=SufficiencyVerdict.INSUFFICIENT,
                score=0.0,
                accepted_count=0,
                gaps=tuple(gaps),
                signals=tuple(signals),
            )

        # ---- gaps from failed signals ---------------------------------
        gap_list: List[SufficiencyGap] = []
        for signal in signals:
            if not signal.applicable:
                continue
            if signal.value + _EPS < signal.target:
                gap_list.append(self._gap_from_signal(signal))

        # A hard-gap check that crashed proved nothing: record it and never
        # let the verdict claim SUFFICIENT without it.
        broken_hard = [
            s for s in signals
            if s.details.get("evaluator_error")
            and _SIGNAL_TO_GAP.get(s.signal_name, (None, None))[1] == GapSeverity.HARD
        ]
        for s in broken_hard:
            gap_list.append(
                SufficiencyGap(
                    gap_type=GapType.EXECUTION_DEGRADED,
                    severity=GapSeverity.HARD,
                    message=f"Sufficiency check {s.signal_name.value} could not run",
                    details={"evaluator_error": True, "signal": s.signal_name.value},
                )
            )

        score = self._score(signals)
        verdict = self._verdict(score, gap_list, by_name.get(SignalName.TERM_COVERAGE))

        return SufficiencyAssessment(
            round_index=inp.round_index,
            verdict=verdict,
            score=round(score, 4),
            accepted_count=accepted_count,
            gaps=tuple(gap_list),
            signals=tuple(signals),
        )

    # ------------------------------------------------------------------
    def _gap_from_signal(self, signal: SufficiencySignal) -> SufficiencyGap:
        gap_type, severity = _SIGNAL_TO_GAP[signal.signal_name]
        return SufficiencyGap(
            gap_type=gap_type,
            severity=severity,
            message=signal.reason,
            details=dict(signal.details),
        )

    def _score(self, signals: Sequence[SufficiencySignal]) -> float:
        weights = self.config.weights
        total_weight = 0.0
        weighted = 0.0
        for signal in signals:
            if not signal.applicable:
                continue
            weight = float(weights.get(signal.signal_name.value, 0.0))
            total_weight += weight
            weighted += weight * max(0.0, min(1.0, signal.value))
        return weighted / total_weight if total_weight > 0 else 0.0

    def _verdict(
        self,
        score: float,
        gaps: Sequence[SufficiencyGap],
        coverage: SufficiencySignal | None,
    ) -> SufficiencyVerdict:
        # Evidence that hardly mentions the question's words is not evidence.
        if (
            coverage is not None
            and coverage.applicable
            and coverage.value + _EPS < self.config.coverage_floor
        ):
            return SufficiencyVerdict.INSUFFICIENT

        if score >= self.config.sufficient_score:
            verdict = SufficiencyVerdict.SUFFICIENT
        elif score >= self.config.partial_score:
            verdict = SufficiencyVerdict.PARTIALLY_SUFFICIENT
        else:
            verdict = SufficiencyVerdict.INSUFFICIENT

        # A serious gap can never hide behind a good average.
        if verdict == SufficiencyVerdict.SUFFICIENT and any(
            g.severity == GapSeverity.HARD for g in gaps
        ):
            verdict = SufficiencyVerdict.PARTIALLY_SUFFICIENT
        return verdict
