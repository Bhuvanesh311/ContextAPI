"""
Unit tests for L04 (Planning & Strategy).

No database, no network. Run from the backend folder:

    python -m pytest tests/retrieval/test_l04_planning.py -v
"""
import pytest

from app.core.enums import (
    AnalysisMethod,
    ExecutionProfile,
    MemoryRequirement,
    QueryComplexity,
    QueryIntent,
    QuerySafetyOutcome,
    RetrievalRequirementType,
)
from app.retrieval.canonical.schemas import RetrievalContract
from app.retrieval.intelligence.schemas import (
    DecompositionResult,
    ObjectIntelligence,
    QueryAnalysisResult,
    QueryIntelligence,
    QuerySafetyAssessment,
    Subquery,
)
from app.retrieval.planning.capabilities import CapabilityRegistry, CapabilityDescriptor
from app.retrieval.planning.exceptions import CapabilityUnavailableError
from app.retrieval.planning.planner import L04Planner
from app.retrieval.planning.schemas import ExecutionLimits, FallbackPolicy
from app.retrieval.planning.strategies import StrategyEngine
from app.retrieval.planning.validator import validate_plan
from app.retrieval.security.enums import AuthorizationDecision
from app.retrieval.security.schemas import ScopedDocument, ScopedRetrievalContract
from app.retrieval.security.profiles import controls_for


# ---------------------------------------------------------------- helpers

# _freeze_dict in planning schemas converts lists → tuples for immutability.
SCOPE = {"document_version_id": {"$in": ("V1", "V2")}}


def _contract(query="What is the rate limit?") -> RetrievalContract:
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.core.enums import RequestSourceType, ExecutionProfile
    return RetrievalContract(
        request_id="REQ001",
        query=query,
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="USR1"),
        scope={"project_id": "PROJ1"},
        profile=ExecutionProfile.STANDARD,
        lifecycle=LifecycleContext(request_id="REQ001", correlation_id="COR001"),
    )


def _scoped(query="What is the rate limit?") -> ScopedRetrievalContract:
    return ScopedRetrievalContract(
        request=_contract(query),
        effective_scope=SCOPE,
        decision=AuthorizationDecision.ALLOW,
        documents=[ScopedDocument(document_id="DOC1", name="a.pdf", document_version_id="V1")],
    )


def _l03(
    query="What is the rate limit?",
    requirements=None,
    decomposed=False,
    subqueries=None,
) -> QueryAnalysisResult:
    if requirements is None:
        requirements = [RetrievalRequirementType.HYBRID]
    subs = []
    if decomposed and subqueries:
        subs = [Subquery(parent_request_id="REQ001", query=q, purpose="sub") for q in subqueries]
    return QueryAnalysisResult(
        request=_scoped(query),
        original_query=query,
        normalized_query=query,
        query_intelligence=QueryIntelligence(
            intent=QueryIntent.FACT_LOOKUP,
            complexity=QueryComplexity.LOW,
            retrieval_requirements=requirements,
        ),
        query_safety=QuerySafetyAssessment(outcome=QuerySafetyOutcome.SAFE),
        decomposition=DecompositionResult(is_decomposed=decomposed, subqueries=subs),
        analysis_method=AnalysisMethod.DETERMINISTIC,
        memory_requirement=MemoryRequirement.NONE,
    )


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    """Give each test a clean registry with the standard 3 capabilities."""
    reg = CapabilityRegistry()
    for cap_id, req_type in [
        ("cap_hybrid", RetrievalRequirementType.HYBRID),
        ("cap_semantic", RetrievalRequirementType.SEMANTIC),
        ("cap_lexical", RetrievalRequirementType.LEXICAL),
    ]:
        reg.register(CapabilityDescriptor(capability_id=cap_id, capability_type=req_type))
    import app.retrieval.planning.strategies as strat_mod
    import app.retrieval.planning.capabilities as cap_mod
    monkeypatch.setattr(strat_mod, "registry", reg)
    monkeypatch.setattr(cap_mod, "registry", reg)
    return reg


# ---------------------------------------------------------------- planner basics

def test_planner_returns_a_valid_plan():
    plan = L04Planner().plan(_l03())
    assert plan.plan_id
    assert plan.request_id == "REQ001"
    assert plan.graph.steps


def test_plan_carries_correlation_id():
    plan = L04Planner().plan(_l03())
    assert plan.correlation_id == "COR001"


def test_plan_effective_scope_matches_l02():
    plan = L04Planner().plan(_l03())
    assert plan.effective_scope == SCOPE


def test_plan_is_frozen():
    plan = L04Planner().plan(_l03())
    with pytest.raises(Exception):
        plan.plan_id = "hacked"


# ---------------------------------------------------------------- steps

def test_hybrid_requirement_maps_to_cap_hybrid():
    plan = L04Planner().plan(_l03(requirements=[RetrievalRequirementType.HYBRID]))
    assert len(plan.graph.steps) == 1
    assert plan.graph.steps[0].capability_id == "cap_hybrid"


def test_each_step_has_unique_step_id():
    plan = L04Planner().plan(_l03(
        decomposed=True,
        subqueries=["What is A?", "What is B?"],
    ))
    ids = [s.step_id for s in plan.graph.steps]
    assert len(ids) == len(set(ids)), "Duplicate step IDs"


def test_decomposed_query_creates_one_step_per_subquery():
    plan = L04Planner().plan(_l03(
        decomposed=True,
        subqueries=["Part A?", "Part B?", "Part C?"],
    ))
    assert len(plan.graph.steps) == 3
    texts = {s.query_binding.query_text for s in plan.graph.steps}
    assert texts == {"Part A?", "Part B?", "Part C?"}


def test_non_decomposed_query_creates_one_step_per_requirement():
    plan = L04Planner().plan(_l03(
        requirements=[RetrievalRequirementType.SEMANTIC, RetrievalRequirementType.LEXICAL],
    ))
    assert len(plan.graph.steps) == 2
    cap_ids = {s.capability_id for s in plan.graph.steps}
    assert cap_ids == {"cap_semantic", "cap_lexical"}


def test_step_scope_equals_effective_scope():
    plan = L04Planner().plan(_l03())
    for step in plan.graph.steps:
        assert dict(step.step_scope) == SCOPE


def test_step_query_text_equals_normalized_query():
    plan = L04Planner().plan(_l03(query="explain rate limiting"))
    assert plan.graph.steps[0].query_binding.query_text == "explain rate limiting"


# ---------------------------------------------------------------- fallback policy

def test_fallback_capabilities_are_populated():
    plan = L04Planner().plan(_l03(requirements=[RetrievalRequirementType.HYBRID]))
    assert plan.fallback_policy is not None
    assert len(plan.fallback_policy.fallback_capabilities) > 0


def test_hybrid_plan_falls_back_to_semantic_and_lexical():
    plan = L04Planner().plan(_l03(requirements=[RetrievalRequirementType.HYBRID]))
    fb = plan.fallback_policy.fallback_capabilities
    assert "cap_semantic" in fb or "cap_lexical" in fb
    assert "cap_hybrid" not in fb  # already the primary


def test_semantic_plan_falls_back_to_other_capabilities():
    plan = L04Planner().plan(_l03(requirements=[RetrievalRequirementType.SEMANTIC]))
    fb = plan.fallback_policy.fallback_capabilities
    assert "cap_semantic" not in fb


def test_fallback_max_attempts_matches_fallback_count():
    plan = L04Planner().plan(_l03())
    fb = plan.fallback_policy
    assert fb.max_attempts == len(fb.fallback_capabilities)


# ---------------------------------------------------------------- execution limits / budget

def test_execution_limits_are_carried_through():
    limits = ExecutionLimits(max_latency_ms=5000, max_rounds=2)
    plan = L04Planner(execution_limits=limits).plan(_l03())
    assert plan.execution_limits.max_latency_ms == 5000
    assert plan.execution_limits.max_rounds == 2


def test_max_tokens_is_carried_into_plan():
    limits = ExecutionLimits(max_latency_ms=10000, max_tokens=512)
    plan = L04Planner(execution_limits=limits).plan(_l03())
    assert plan.execution_limits.max_tokens == 512


def test_max_cost_is_carried_into_plan():
    limits = ExecutionLimits(max_latency_ms=10000, max_cost=0.05)
    plan = L04Planner(execution_limits=limits).plan(_l03())
    assert plan.execution_limits.max_cost == pytest.approx(0.05)


def test_none_token_budget_is_allowed():
    limits = ExecutionLimits(max_tokens=None, max_cost=None)
    plan = L04Planner(execution_limits=limits).plan(_l03())
    assert plan.execution_limits.max_tokens is None
    assert plan.execution_limits.max_cost is None


# ---------------------------------------------------------------- capability errors

def test_missing_capability_raises():
    from app.retrieval.planning.capabilities import CapabilityRegistry
    import app.retrieval.planning.strategies as strat_mod
    empty_reg = CapabilityRegistry()
    strat_mod.registry = empty_reg
    with pytest.raises(CapabilityUnavailableError):
        L04Planner().plan(_l03())


# ---------------------------------------------------------------- validator

def test_validator_rejects_plan_with_empty_query():
    from app.retrieval.planning.exceptions import QueryBindingFailureError
    plan = L04Planner().plan(_l03())
    bad_step = plan.graph.steps[0].model_copy(
        update={"query_binding": plan.graph.steps[0].query_binding.model_copy(update={"query_text": "   "})}
    )
    from app.retrieval.planning.schemas import ExecutionGraph
    bad_plan = plan.model_copy(update={"graph": ExecutionGraph(steps=(bad_step,))})
    with pytest.raises(QueryBindingFailureError):
        validate_plan(bad_plan)


# ---------------------------------------------------------------- profile step limits

def test_subqueries_trimmed_to_fit_max_steps_instead_of_failing():
    limits = ExecutionLimits(max_steps=5, max_subqueries=5)
    plan = L04Planner(execution_limits=limits).plan(_l03(
        requirements=[RetrievalRequirementType.HYBRID, RetrievalRequirementType.LEXICAL],
        decomposed=True,
        subqueries=["Part A?", "Part B?", "Part C?"],
    ))
    assert len(plan.graph.steps) <= 5
    assert len(plan.graph.steps) == 4


def test_max_subqueries_caps_decomposed_steps():
    limits = ExecutionLimits(max_steps=8, max_subqueries=2)
    plan = L04Planner(execution_limits=limits).plan(_l03(
        decomposed=True,
        subqueries=["Part A?", "Part B?", "Part C?"],
    ))
    assert len(plan.graph.steps) == 2


def test_fast_profile_step_limit_respected():
    fast = controls_for(ExecutionProfile.FAST)
    limits = ExecutionLimits(max_steps=fast.max_steps, max_subqueries=fast.max_subqueries)
    plan = L04Planner(execution_limits=limits).plan(_l03(
        requirements=[
            RetrievalRequirementType.HYBRID,
            RetrievalRequirementType.SEMANTIC,
            RetrievalRequirementType.LEXICAL,
        ],
        decomposed=True,
        subqueries=["Part A?", "Part B?"],
    ))
    assert len(plan.graph.steps) <= fast.max_steps


def test_subqueries_over_step_budget_are_folded_not_dropped():
    limits = ExecutionLimits(max_steps=8, max_subqueries=2)
    plan = L04Planner(execution_limits=limits).plan(_l03(
        decomposed=True,
        subqueries=["Part A?", "Part B?", "Part C?"],
    ))
    texts = [s.query_binding.query_text for s in plan.graph.steps]
    assert texts == ["Part A?", "Part B? and Part C?"]
