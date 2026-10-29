import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.core.enums import RetrievalRequirementType
from app.retrieval.planning.capabilities import CapabilityRegistry, registry as global_registry
from app.retrieval.planning.exceptions import CapabilityUnavailableError
from app.retrieval.planning.schemas import (
    ExecutionGraph,
    QueryBinding,
    RetrievalPlan,
    RetrievalStep,
)
from app.retrieval.planning.validator import validate_plan
from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.enums import EscalationAction, GapType
from app.retrieval.sufficiency.models import (
    EscalationDecision,
    EscalationStepSpec,
    SufficiencyAssessment,
    SufficiencyGap,
    SufficiencyQuery,
)

# Which gap is looked at first.
GAP_PRIORITY: Tuple[GapType, ...] = (
    GapType.NO_EVIDENCE,
    GapType.EXECUTION_DEGRADED,
    GapType.SUBQUERY_UNCOVERED,
    GapType.LOW_TERM_COVERAGE,
    GapType.TOO_FEW_EVIDENCE,
    GapType.LOW_SOURCE_DIVERSITY,
    GapType.LOW_CONTENT,
)

# For each gap, the actions to try, best first. Gaps that are not listed
# here (WEAK_AGREEMENT, CONFLICT_UNRESOLVED) cannot be fixed by searching
# more, so they are reported and never escalated.
GAP_ACTIONS: Dict[GapType, Tuple[EscalationAction, ...]] = {
    GapType.NO_EVIDENCE: (
        EscalationAction.SPLIT_RETRIEVERS,
        EscalationAction.KEYWORD_REWRITE,
        EscalationAction.WIDEN_DEPTH,
    ),
    GapType.EXECUTION_DEGRADED: (
        EscalationAction.SPLIT_RETRIEVERS,
        EscalationAction.WIDEN_DEPTH,
        EscalationAction.KEYWORD_REWRITE,
    ),
    GapType.SUBQUERY_UNCOVERED: (
        EscalationAction.TARGET_SUBQUERIES,
        EscalationAction.GAP_FOCUSED_QUERY,
        EscalationAction.WIDEN_DEPTH,
    ),
    GapType.LOW_TERM_COVERAGE: (
        EscalationAction.GAP_FOCUSED_QUERY,
        EscalationAction.WIDEN_DEPTH,
        EscalationAction.KEYWORD_REWRITE,
    ),
    GapType.TOO_FEW_EVIDENCE: (
        EscalationAction.WIDEN_DEPTH,
        EscalationAction.KEYWORD_REWRITE,
    ),
    GapType.LOW_SOURCE_DIVERSITY: (
        EscalationAction.WIDEN_DEPTH,
        EscalationAction.KEYWORD_REWRITE,
    ),
    GapType.LOW_CONTENT: (
        EscalationAction.WIDEN_DEPTH,
        EscalationAction.KEYWORD_REWRITE,
    ),
}

_MAX_FOCUSED_TERMS = 6
_ANCHOR_TERMS = 2


@dataclass
class EscalationState:
    """Memory of the loop, so the same thing is never tried twice."""
    current_top_k: int
    applied: Set[EscalationAction] = field(default_factory=set)
    tried: Set[tuple] = field(default_factory=set)

    def record(self, decision: EscalationDecision) -> None:
        self.applied.add(decision.action)
        self.tried.add(_signature(decision))
        self.current_top_k = decision.top_k


def _signature(decision: EscalationDecision) -> tuple:
    return (
        tuple((s.capability_type.value, s.query_text.lower()) for s in decision.steps),
        decision.top_k,
    )


class EscalationPlanner:
    """
    Picks the next escalation step (deterministic ladder) and turns it
    into a validated RetrievalPlan.

    Security: every step of an escalation plan copies the base plan's
    effective_scope unchanged and the plan goes through validate_plan()
    again. Escalation can search deeper or differently, but it can never
    search wider than L02 allowed.
    """

    def __init__(
        self,
        config: SufficiencyConfig,
        capability_registry: Optional[CapabilityRegistry] = None,
    ):
        self.config = config
        self._registry = capability_registry or global_registry

    # ------------------------------------------------------------------
    def next_decision(
        self,
        assessment: SufficiencyAssessment,
        query: SufficiencyQuery,
        state: EscalationState,
        max_steps: int,
        max_subqueries: int,
    ) -> Optional[EscalationDecision]:
        gaps_by_type = {g.gap_type: g for g in assessment.gaps}
        for gap_type in GAP_PRIORITY:
            gap = gaps_by_type.get(gap_type)
            if gap is None:
                continue
            for action in GAP_ACTIONS.get(gap_type, ()):
                if action in state.applied:
                    continue
                decision = self._build(action, gap, query, state, max_steps, max_subqueries)
                if decision is None:
                    continue
                if _signature(decision) in state.tried:
                    continue
                return decision
        return None

    def build_plan(
        self,
        base_plan: RetrievalPlan,
        decision: EscalationDecision,
        round_index: int,
        remaining_ms: int,
    ) -> RetrievalPlan:
        steps: List[RetrievalStep] = []
        for spec in decision.steps:
            capabilities = self._registry.get_eligible_capabilities(spec.capability_type)
            if not capabilities:
                raise CapabilityUnavailableError(
                    f"No available capability for {spec.capability_type}"
                )
            steps.append(
                RetrievalStep(
                    capability_id=capabilities[0].capability_id,
                    query_binding=QueryBinding(
                        binding_type="escalation",
                        query_text=spec.query_text,
                        subquery_id=spec.subquery_id,
                    ),
                    step_scope=base_plan.effective_scope,   # never widened
                    depends_on=(),
                )
            )

        limits = base_plan.execution_limits.model_copy(
            update={
                "max_latency_ms": max(
                    0, min(base_plan.execution_limits.max_latency_ms, int(remaining_ms))
                )
            }
        )
        plan = base_plan.model_copy(
            update={
                "plan_id": str(uuid.uuid4()),
                "graph": ExecutionGraph(steps=tuple(steps)),
                "execution_limits": limits,
                "planning_summary": (
                    f"L07 escalation round {round_index}: {decision.action.value}"
                ),
            }
        )
        return validate_plan(plan)

    # ------------------------------------------------------------------
    def _has(self, capability_type: RetrievalRequirementType) -> bool:
        return bool(self._registry.get_eligible_capabilities(capability_type))

    def _decision(
        self,
        action: EscalationAction,
        reason: str,
        top_k: int,
        steps: Sequence[EscalationStepSpec],
        max_steps: int,
    ) -> Optional[EscalationDecision]:
        steps = tuple(steps)[:max_steps]
        if not steps:
            return None
        if not all(self._has(s.capability_type) for s in steps):
            return None
        return EscalationDecision(action=action, reason=reason, top_k=top_k, steps=steps)

    def _build(
        self,
        action: EscalationAction,
        gap: SufficiencyGap,
        query: SufficiencyQuery,
        state: EscalationState,
        max_steps: int,
        max_subqueries: int,
    ) -> Optional[EscalationDecision]:
        H = RetrievalRequirementType.HYBRID
        base_text = query.query_text
        top_k = state.current_top_k

        if action == EscalationAction.WIDEN_DEPTH:
            new_k = min(self.config.max_top_k, top_k * self.config.top_k_growth_factor)
            if new_k <= top_k:
                return None
            return self._decision(
                action, f"Searching deeper (top_k {top_k} -> {new_k})", new_k,
                [EscalationStepSpec(capability_type=H, query_text=base_text)], max_steps,
            )

        if action == EscalationAction.TARGET_SUBQUERIES:
            missing = list(gap.details.get("uncovered_subqueries", []))[:max_subqueries]
            return self._decision(
                action, f"Searching {len(missing)} uncovered sub-questions", top_k,
                [EscalationStepSpec(capability_type=H, query_text=text) for text in missing],
                max_steps,
            )

        if action == EscalationAction.GAP_FOCUSED_QUERY:
            uncovered = list(gap.details.get("uncovered_terms", []))[:_MAX_FOCUSED_TERMS]
            if not uncovered:
                return None
            covered = list(gap.details.get("covered_terms", []))[:_ANCHOR_TERMS]
            text = " ".join(covered + uncovered)
            return self._decision(
                action, f"Searching for missing terms: {', '.join(uncovered)}", top_k,
                [EscalationStepSpec(capability_type=H, query_text=text)], max_steps,
            )

        if action == EscalationAction.KEYWORD_REWRITE:
            text = " ".join(query.terms)
            if not text or text.lower() == base_text.strip().lower():
                return None
            return self._decision(
                action, "Searching with keywords only", top_k,
                [EscalationStepSpec(capability_type=H, query_text=text)], max_steps,
            )

        if action == EscalationAction.SPLIT_RETRIEVERS:
            return self._decision(
                action, "Running semantic and lexical search separately", top_k,
                [
                    EscalationStepSpec(
                        capability_type=RetrievalRequirementType.SEMANTIC, query_text=base_text
                    ),
                    EscalationStepSpec(
                        capability_type=RetrievalRequirementType.LEXICAL, query_text=base_text
                    ),
                ],
                max_steps,
            )

        return None
