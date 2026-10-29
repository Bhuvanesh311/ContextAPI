import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from app.retrieval.engine.schemas import CandidateEvidence, CandidateEvidenceSet, _freeze_dict
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import ValidatedEvidence, ValidatedEvidenceSet
from app.retrieval.planning.exceptions import L04PlanningError
from app.retrieval.planning.schemas import RetrievalPlan
from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.enums import (
    EscalationAction,
    StopReason,
    SufficiencyVerdict,
)
from app.retrieval.sufficiency.escalation import EscalationPlanner, EscalationState
from app.retrieval.sufficiency.evaluators.base import AssessmentInput
from app.retrieval.sufficiency.models import (
    EscalationDecision,
    RoundRecord,
    SufficiencyAssessment,
    SufficiencyQuery,
    SufficiencyReport,
)
from app.retrieval.sufficiency.service import SufficiencyService

logger = logging.getLogger(__name__)

# execute_fn(plan, top_k)   -> raw result of one retrieval round (L05)
# evidence_fn(candidate_set) -> validated evidence (L06)
ExecuteFn = Callable[[RetrievalPlan, int], CandidateEvidenceSet]
EvidenceFn = Callable[[CandidateEvidenceSet], ValidatedEvidenceSet]

_ROUND_KEY = "l7_round"
_ACTION_KEY = "l7_action"


@dataclass(frozen=True)
class RetrievalOutcome:
    """What the caller gets back: the final evidence and the explanation."""
    evidence: Tuple[ValidatedEvidence, ...]
    report: SufficiencyReport


class ProgressiveRetrievalController:
    """
    L07: run retrieval, judge whether the evidence is enough, and if not,
    escalate step by step until it is enough or a limit is hit.

        round 0  -> the plan L04 made
        round 1+ -> a plan built by EscalationPlanner from the gaps found

    The controller knows nothing about databases or vector stores. L05 and
    L06 are handed in as functions, which keeps this class fast to unit test.

    Guarantees:
      * Round 0 exceptions propagate (the caller decides how to fail).
        Exceptions in later rounds are logged and the loop stops, keeping
        everything found so far. Escalation can only add to a result.
      * Never searches wider than the base plan's effective_scope.
      * Bounded by max_rounds, a total latency budget, and a no-progress rule.
    """

    def __init__(
        self,
        *,
        config: SufficiencyConfig,
        execute_fn: ExecuteFn,
        evidence_fn: EvidenceFn,
        sufficiency: Optional[SufficiencyService] = None,
        planner: Optional[EscalationPlanner] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        config.validate_config()
        self.config = config
        self.execute_fn = execute_fn
        self.evidence_fn = evidence_fn
        self.sufficiency = sufficiency or SufficiencyService(config)
        self.planner = planner or EscalationPlanner(config)
        self._clock = clock

    # ------------------------------------------------------------------
    def run(
        self,
        base_plan: RetrievalPlan,
        query: SufficiencyQuery,
        top_k: int,
        request_id: str = "",
    ) -> RetrievalOutcome:
        cfg = self.config
        limits = base_plan.execution_limits
        max_rounds = max(1, min(cfg.max_rounds, limits.max_rounds))

        start = self._clock()

        def elapsed_ms() -> int:
            return int((self._clock() - start) * 1000)

        state = EscalationState(current_top_k=top_k)
        merged: Dict[str, CandidateEvidence] = {}
        records: List[RoundRecord] = []

        plan = self._with_budget(base_plan, cfg.max_total_latency_ms)
        decision: Optional[EscalationDecision] = None
        previous_accepted = 0
        no_progress_streak = 0

        assessment: Optional[SufficiencyAssessment] = None
        accepted: Tuple[ValidatedEvidence, ...] = ()
        stop_reason = StopReason.MAX_ROUNDS_REACHED

        for round_index in range(max_rounds):
            round_start = self._clock()

            # ---- L05: execute ---------------------------------------
            try:
                latest = self.execute_fn(plan, state.current_top_k)
            except Exception:
                if round_index == 0:
                    raise
                logger.exception("L7 round %s execution failed, keeping earlier evidence", round_index)
                stop_reason = StopReason.EXECUTION_ERROR
                break

            new_candidates = self._merge(merged, latest, round_index, decision)
            merged_set = CandidateEvidenceSet(
                plan_id=base_plan.plan_id,
                status=latest.status,
                candidates=tuple(merged.values()),
                traces=latest.traces,
                total_latency_ms=latest.total_latency_ms,
                fatal_error=latest.fatal_error,
            )

            # ---- L06: validate the merged evidence -------------------
            try:
                validated = self.evidence_fn(merged_set)
            except Exception:
                if round_index == 0:
                    raise
                logger.exception("L7 round %s evidence evaluation failed", round_index)
                stop_reason = StopReason.EXECUTION_ERROR
                break

            all_validated = tuple(validated.validated_evidence)
            accepted = tuple(ve for ve in all_validated if ve.state == EvidenceState.ACCEPTED)

            # ---- L07: judge ---------------------------------------------
            assessment = self.sufficiency.assess(
                AssessmentInput(
                    query=query,
                    accepted=accepted,
                    all_validated=all_validated,
                    latest_round=latest,
                    round_index=round_index,
                    top_k=state.current_top_k,
                )
            )

            new_accepted = len(accepted) - previous_accepted
            previous_accepted = len(accepted)
            records.append(
                RoundRecord(
                    round_index=round_index,
                    action=decision.action if decision else None,
                    reason=decision.reason if decision else None,
                    queries=tuple(s.query_binding.query_text for s in plan.graph.steps),
                    top_k=state.current_top_k,
                    execution_status=latest.status.value,
                    new_candidates=new_candidates,
                    accepted_total=len(accepted),
                    new_accepted=new_accepted,
                    verdict=assessment.verdict,
                    score=assessment.score,
                    gap_types=tuple(g.gap_type for g in assessment.gaps),
                    latency_ms=int((self._clock() - round_start) * 1000),
                )
            )
            logger.info(
                "L7 request=%s round=%s action=%s verdict=%s score=%.2f accepted=%s new=%s",
                request_id, round_index, decision.action.value if decision else "-",
                assessment.verdict.value, assessment.score, len(accepted), new_accepted,
            )

            # ---- decide: stop or escalate --------------------------------
            if assessment.verdict == SufficiencyVerdict.SUFFICIENT:
                stop_reason = StopReason.SUFFICIENT
                break

            if round_index > 0:
                no_progress_streak = no_progress_streak + 1 if new_accepted <= 0 else 0
                if no_progress_streak >= cfg.max_consecutive_no_progress:
                    stop_reason = StopReason.NO_PROGRESS
                    break

            if round_index + 1 >= max_rounds:
                stop_reason = StopReason.MAX_ROUNDS_REACHED
                break

            remaining_ms = cfg.max_total_latency_ms - elapsed_ms()
            if remaining_ms < cfg.min_round_budget_ms:
                stop_reason = StopReason.DEADLINE_EXCEEDED
                break

            decision = self.planner.next_decision(
                assessment,
                query,
                state,
                max_steps=limits.max_steps,
                max_subqueries=limits.max_subqueries,
            )
            if decision is None:
                stop_reason = StopReason.NO_ESCALATION_AVAILABLE
                break

            try:
                plan = self.planner.build_plan(base_plan, decision, round_index + 1, remaining_ms)
            except L04PlanningError:
                logger.exception("L7 escalation plan rejected (%s)", decision.action.value)
                stop_reason = StopReason.ESCALATION_REJECTED
                decision = None
                break
            state.record(decision)

        if assessment is None:
            raise RuntimeError(
                "BUG: L07 exited without producing an assessment "
                "(max_rounds guarantee violated — round 0 should have raised)"
            )

        result_limit = state.current_top_k if cfg.allow_top_k_growth else top_k
        final = self._select_final(accepted, result_limit)
        report = SufficiencyReport(
            verdict=assessment.verdict,
            score=assessment.score,
            stop_reason=stop_reason,
            rounds_executed=len(records),
            max_rounds=max_rounds,
            escalated=len(records) > 1,
            result_limit=result_limit,
            total_latency_ms=elapsed_ms(),
            gaps=assessment.gaps,
            signals=assessment.signals,
            rounds=tuple(records),
        )
        return RetrievalOutcome(evidence=final, report=report)

    # ------------------------------------------------------------------
    def _with_budget(self, plan: RetrievalPlan, budget_ms: int) -> RetrievalPlan:
        current = plan.execution_limits.max_latency_ms
        if current <= budget_ms:
            return plan
        limits = plan.execution_limits.model_copy(update={"max_latency_ms": budget_ms})
        return plan.model_copy(update={"execution_limits": limits})

    @staticmethod
    def _merge(
        merged: Dict[str, CandidateEvidence],
        latest: CandidateEvidenceSet,
        round_index: int,
        decision: Optional[EscalationDecision],
    ) -> int:
        """Add new chunks. A chunk seen before keeps its first (earliest round) copy."""
        added = 0
        for candidate in latest.candidates:
            key = candidate.provenance.chunk_id or candidate.evidence_id
            if key in merged:
                continue
            metadata = dict(candidate.retrieval_metadata or {})
            metadata[_ROUND_KEY] = round_index
            if decision is not None:
                metadata[_ACTION_KEY] = decision.action.value
            merged[key] = candidate.model_copy(
                update={"retrieval_metadata": _freeze_dict(metadata)}
            )
            added += 1
        return added

    def _select_final(
        self,
        accepted: Tuple[ValidatedEvidence, ...],
        limit: int,
    ) -> Tuple[ValidatedEvidence, ...]:
        """
        Original results first (they matched the question as asked), escalation
        results after them. Scores from different rounds and different search
        types are not comparable, so round comes before score.
        """
        ordered = sorted(
            accepted,
            key=lambda ve: (
                int((ve.candidate.retrieval_metadata or {}).get(_ROUND_KEY, 0)),
                -ve.candidate.score,
            ),
        )
        return tuple(ordered[:limit])
