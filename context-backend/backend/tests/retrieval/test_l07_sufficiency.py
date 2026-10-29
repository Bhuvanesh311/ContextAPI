"""
Unit tests for L07 (Sufficiency, Gap Detection & Progressive Escalation).

No database, no ChromaDB, no network: L05 and L06 are replaced by small
fakes, so these run in milliseconds.  Run from the backend folder:

    python -m pytest tests/retrieval/test_l07_sufficiency.py -v
"""
from unittest import mock

from app.core.enums import QueryComplexity, QueryIntent, RetrievalRequirementType
from app.retrieval.engine.enums import ExecutionStatus, OperatorType
from app.retrieval.engine.schemas import (
    CandidateEvidence,
    CandidateEvidenceSet,
    ExecutionTrace,
    ProvenanceMetadata,
)
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.models import ValidatedEvidence, ValidatedEvidenceSet
from app.retrieval.planning.capabilities import CapabilityRegistry
from app.retrieval.planning.exceptions import PlanValidationFailedError
from app.retrieval.planning.schemas import (
    CapabilityDescriptor,
    ExecutionGraph,
    ExecutionLimits,
    QueryBinding,
    RetrievalPlan,
    RetrievalStep,
    StopConditions,
)
from app.retrieval.sufficiency.config import SufficiencyConfig
from app.retrieval.sufficiency.controller import ProgressiveRetrievalController
from app.retrieval.sufficiency.enums import (
    EscalationAction,
    GapType,
    SignalName,
    StopReason,
    SufficiencyVerdict,
)
from app.retrieval.sufficiency.escalation import EscalationPlanner
from app.retrieval.sufficiency.evaluators.base import AssessmentInput
from app.retrieval.sufficiency.exceptions import SufficiencyConfigError
from app.retrieval.sufficiency.models import SufficiencyQuery
from app.retrieval.sufficiency.service import SufficiencyService
from app.retrieval.sufficiency.text import significant_terms

SCOPE = {"document_version_id": {"$in": ["V1", "V2", "V3"]}}
LONG = " Additional supporting sentence about the same topic to give the chunk some real length." * 3


# ---------------------------------------------------------------- helpers
def cand(chunk_id, content, score=0.03, doc="DOC1", matched_by="lexical+semantic"):
    prov = ProvenanceMetadata(
        document_id=doc, document_version_id="V1", chunk_id=chunk_id,
        source_type="postgres", step_id="s", operator_type=OperatorType.SEMANTIC,
    )
    meta = {"matched_by": matched_by} if matched_by else {}
    return CandidateEvidence(content=content + LONG, provenance=prov, score=score, retrieval_metadata=meta)


def registry(hybrid=True, semantic=True, lexical=True):
    reg = CapabilityRegistry()
    if semantic:
        reg.register(CapabilityDescriptor(capability_id="cap_semantic", capability_type=RetrievalRequirementType.SEMANTIC))
    if lexical:
        reg.register(CapabilityDescriptor(capability_id="cap_lexical", capability_type=RetrievalRequirementType.LEXICAL))
    if hybrid:
        reg.register(CapabilityDescriptor(capability_id="cap_hybrid", capability_type=RetrievalRequirementType.HYBRID))
    return reg


def base_plan(max_rounds=3):
    return RetrievalPlan(
        request_id="R1", correlation_id="R1", effective_scope=SCOPE, planning_summary="test",
        graph=ExecutionGraph(steps=(RetrievalStep(
            capability_id="cap_hybrid",
            query_binding=QueryBinding(binding_type="normalized", query_text="q"),
            step_scope=SCOPE),)),
        execution_limits=ExecutionLimits(max_latency_ms=60000, max_rounds=max_rounds),
        stop_conditions=StopConditions(),
    )


def round_result(plan, candidates, status=ExecutionStatus.SUCCESS, failed=False):
    traces = tuple(
        ExecutionTrace(step_id=s.step_id, operator_type=OperatorType.SEMANTIC,
                       status=ExecutionStatus.FAILED if failed else ExecutionStatus.SUCCESS,
                       error_message="boom" if failed else None)
        for s in plan.graph.steps
    )
    return CandidateEvidenceSet(plan_id=plan.plan_id, status=status, candidates=tuple(candidates), traces=traces)


def accept_all(candidate_set):
    return ValidatedEvidenceSet(
        plan_id=candidate_set.plan_id,
        original_candidates_count=len(candidate_set.candidates),
        validated_evidence=tuple(
            ValidatedEvidence(evidence_id=c.evidence_id, candidate=c,
                              state=EvidenceState.ACCEPTED, primary_reason="ok")
            for c in candidate_set.candidates
        ),
    )


class Script:
    """execute_fn that returns a prepared list of candidate lists, one per round."""
    def __init__(self, *rounds, failed_rounds=()):
        self.rounds, self.failed_rounds = list(rounds), set(failed_rounds)
        self.plans, self.top_ks = [], []

    def __call__(self, plan, top_k):
        i = len(self.plans)
        self.plans.append(plan)
        self.top_ks.append(top_k)
        item = self.rounds[min(i, len(self.rounds) - 1)]
        if isinstance(item, Exception):
            raise item
        return round_result(plan, item, failed=i in self.failed_rounds)


def controller(script, config=None, reg=None, clock=None):
    config = config or SufficiencyConfig()
    kwargs = {"clock": clock} if clock else {}
    return ProgressiveRetrievalController(
        config=config, execute_fn=script, evidence_fn=accept_all,
        planner=EscalationPlanner(config, reg or registry()), **kwargs,
    )


def query(text, intent=QueryIntent.FACT_LOOKUP, complexity=QueryComplexity.LOW, subs=(), docs=3):
    return SufficiencyQuery.create(text, intent, complexity, subs, docs)


# ------------------------------------------------------------------ text
def test_significant_terms_drop_filler_words():
    terms = [s for s, _ in significant_terms("Explain the rate limiting of payments API")]
    assert terms == ["rate", "limiting", "payments", "api"]


def test_generic_verb_work_is_not_a_topic_term():
    # "how does billing work" is about billing. "work" must not count as a match.
    terms = [s for s, _ in significant_terms("how does billing work")]
    assert terms == ["billing"]


def test_words_about_the_documents_are_not_topic_terms():
    # "full details about the pdf" names the document, not a topic in it.
    assert significant_terms("full details about pdf?") == []
    assert [s for s, _ in significant_terms("project pathi full details kudu")] == ["project"]


def test_stem_matches_plural_and_ing():
    stems = dict((s, st) for s, st in significant_terms("payments crawling"))
    assert stems["payments"] == "payment" and stems["crawling"] == "crawl"


# ---------------------------------------------------------- assessment
def _assess(text, cands, **qkw):
    validated = accept_all(CandidateEvidenceSet(plan_id="P", status=ExecutionStatus.SUCCESS, candidates=tuple(cands)))
    accepted = validated.validated_evidence
    plan = base_plan()
    inp = AssessmentInput(
        query=query(text, **qkw), accepted=accepted, all_validated=accepted,
        latest_round=round_result(plan, cands), round_index=0, top_k=5,
    )
    return SufficiencyService(SufficiencyConfig()).assess(inp)


def test_good_evidence_is_sufficient():
    a = _assess("what is contextapi", [cand("c1", "ContextAPI is a platform"), cand("c2", "ContextAPI docs"), cand("c3", "ContextAPI usage")])
    assert a.verdict == SufficiencyVerdict.SUFFICIENT and a.score > 0.9 and not a.gaps


def test_no_evidence_is_insufficient_with_no_evidence_gap():
    a = _assess("what is contextapi", [])
    assert a.verdict == SufficiencyVerdict.INSUFFICIENT
    assert [g.gap_type for g in a.gaps] == [GapType.NO_EVIDENCE]


def test_evidence_that_ignores_the_question_is_insufficient():
    a = _assess("explain rate limiting for payments api", [cand("c1", "The api is written in python"), cand("c2", "api keys")])
    assert a.verdict == SufficiencyVerdict.INSUFFICIENT
    gap = next(g for g in a.gaps if g.gap_type == GapType.LOW_TERM_COVERAGE)
    assert "rate" in gap.details["uncovered_terms"] and gap.details["covered_terms"] == ["api"]


def test_overview_question_is_not_rejected_for_missing_filler_words():
    # Before: "full", "details", "pdf" counted as topic words, coverage was 0,
    # and the floor rule made any overview question INSUFFICIENT.
    a = _assess("full details about pdf?", [cand("c1", "Functional requirements of the platform"),
                                             cand("c2", "Step 1: ingestion and discovery")])
    assert a.verdict != SufficiencyVerdict.INSUFFICIENT
    assert not any(g.gap_type == GapType.LOW_TERM_COVERAGE for g in a.gaps)


def test_hard_gap_caps_a_good_average():
    # good coverage/quantity but a comparison answered from one document
    a = _assess("compare auth and billing", [cand("c1", "auth billing compare"), cand("c2", "auth billing")],
                intent=QueryIntent.COMPARISON, docs=3)
    assert any(g.gap_type == GapType.LOW_SOURCE_DIVERSITY for g in a.gaps)
    assert a.verdict == SufficiencyVerdict.PARTIALLY_SUFFICIENT


def test_source_target_never_exceeds_available_documents():
    a = _assess("compare auth and billing", [cand("c1", "auth billing"), cand("c2", "auth billing")],
                intent=QueryIntent.COMPARISON, docs=1)
    assert not any(g.gap_type == GapType.LOW_SOURCE_DIVERSITY for g in a.gaps)


def test_a_broken_evaluator_does_not_break_assessment():
    class Boom:
        name = SignalName.TERM_COVERAGE
        def evaluate(self, inp): raise RuntimeError("bug")
    svc = SufficiencyService(SufficiencyConfig(), evaluators=[Boom()])
    plan = base_plan()
    inp = AssessmentInput(query=query("what is x"), accepted=(), all_validated=(),
                          latest_round=round_result(plan, []), round_index=0, top_k=5)
    assert svc.assess(inp).verdict == SufficiencyVerdict.INSUFFICIENT


def test_bad_config_is_rejected():
    for bad in (SufficiencyConfig(max_rounds=0), SufficiencyConfig(partial_score=0.9, sufficient_score=0.5),
                SufficiencyConfig(top_k_growth_factor=1)):
        try:
            bad.validate_config()
        except SufficiencyConfigError:
            continue
        raise AssertionError("config should have been rejected")


# ------------------------------------------------------------ controller
def test_sufficient_first_round_means_no_escalation_and_same_order_as_before():
    script = Script([cand("c1", "ContextAPI a", 0.01), cand("c2", "ContextAPI b", 0.03), cand("c3", "ContextAPI c", 0.02)])
    out = controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    assert out.report.verdict == SufficiencyVerdict.SUFFICIENT
    assert out.report.stop_reason == StopReason.SUFFICIENT
    assert out.report.rounds_executed == 1 and not out.report.escalated
    assert [ve.candidate.provenance.chunk_id for ve in out.evidence] == ["c2", "c3", "c1"]  # score desc
    assert len(script.plans) == 1


def test_no_evidence_first_tries_split_retrievers_then_succeeds():
    script = Script([], [cand("c1", "ContextAPI a"), cand("c2", "ContextAPI b"), cand("c3", "ContextAPI c")])
    out = controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    assert out.report.rounds_executed == 2 and out.report.escalated
    assert out.report.rounds[1].action == EscalationAction.SPLIT_RETRIEVERS
    assert [s.capability_id for s in script.plans[1].graph.steps] == ["cap_semantic", "cap_lexical"]
    assert out.report.verdict == SufficiencyVerdict.SUFFICIENT


def test_low_coverage_builds_gap_focused_query():
    script = Script(
        [cand("c1", "The api overview"), cand("c2", "api keys")],
        [cand("c3", "Rate limiting for payments is 100 per minute")],
    )
    out = controller(script).run(base_plan(), query("explain rate limiting for payments api"), top_k=5)
    round1 = out.report.rounds[1]
    assert round1.action == EscalationAction.GAP_FOCUSED_QUERY
    assert round1.queries == ("api rate limiting payments",)
    assert out.report.verdict == SufficiencyVerdict.SUFFICIENT
    # original evidence first, escalated evidence after
    assert [ve.candidate.provenance.chunk_id for ve in out.evidence][-1] == "c3"


def test_uncovered_subquery_is_searched_on_its_own():
    q = query("what is auth and how does billing work", complexity=QueryComplexity.HIGH,
              subs=("what is auth", "how does billing work"))
    script = Script([cand("c1", "auth login tokens"), cand("c2", "auth roles")],
                    [cand("c3", "billing is monthly and invoices are generated")])
    out = controller(script).run(base_plan(), q, top_k=5)
    assert out.report.rounds[1].action == EscalationAction.TARGET_SUBQUERIES
    assert out.report.rounds[1].queries == ("how does billing work",)


def test_diversity_gap_widens_depth_and_top_k_growth_is_reported():
    q = query("compare auth and billing", intent=QueryIntent.COMPARISON)
    script = Script([cand("c1", "auth billing compare"), cand("c2", "auth billing")],
                    [cand("c3", "auth billing other document", doc="DOC2")])
    out = controller(script).run(base_plan(), q, top_k=5)
    assert script.top_ks == [5, 10]
    assert out.report.rounds[1].action == EscalationAction.WIDEN_DEPTH
    assert out.report.result_limit == 10 and out.report.verdict == SufficiencyVerdict.SUFFICIENT


def test_top_k_growth_can_be_switched_off():
    q = query("compare auth and billing", intent=QueryIntent.COMPARISON)
    many = [cand(f"c{i}", "auth billing text", score=0.03 - i / 1000) for i in range(8)]
    script = Script(many[:2], many + [cand("x", "auth billing", doc="DOC2")])
    out = controller(script, SufficiencyConfig(allow_top_k_growth=False)).run(base_plan(), q, top_k=5)
    assert out.report.result_limit == 5 and len(out.evidence) <= 5


def test_escalation_never_widens_scope():
    script = Script([], [], [])
    controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    assert len(script.plans) >= 2
    # The planner freezes scopes (list -> tuple), so compare with the frozen
    # scope of the base plan instead of the raw list-based SCOPE constant.
    expected = base_plan().effective_scope
    for plan in script.plans:
        assert plan.effective_scope == expected
        for step in plan.graph.steps:
            assert step.step_scope == expected


def test_rejected_escalation_plan_stops_loop_safely():
    script = Script([cand("c1", "auth")])
    with mock.patch("app.retrieval.sufficiency.escalation.validate_plan",
                    side_effect=PlanValidationFailedError("scope")):
        out = controller(script).run(base_plan(), query("explain rate limiting for payments api"), top_k=5)
    assert out.report.stop_reason == StopReason.ESCALATION_REJECTED
    assert out.report.rounds_executed == 1 and len(out.evidence) == 1  # evidence kept


def test_max_rounds_is_respected_and_plan_limit_can_lower_it():
    script = Script([cand("c1", "auth")], [cand("c1", "auth")], [cand("c1", "auth")], [cand("c1", "auth")])
    out = controller(script).run(base_plan(max_rounds=2), query("explain rate limiting for payments api"), top_k=5)
    assert out.report.rounds_executed <= 2 and out.report.max_rounds == 2


def test_no_progress_stops_the_loop():
    script = Script([cand("c1", "auth")])   # same single chunk every round
    cfg = SufficiencyConfig(max_rounds=6, max_consecutive_no_progress=2)
    out = controller(script, cfg).run(base_plan(max_rounds=6), query("explain rate limiting for payments api"), top_k=5)
    assert out.report.stop_reason in (StopReason.NO_PROGRESS, StopReason.NO_ESCALATION_AVAILABLE)
    assert out.report.rounds_executed <= 4


def test_deadline_stops_before_another_round():
    ticks = iter(range(0, 10_000, 30))     # every clock() call moves 30 seconds
    script = Script([cand("c1", "auth")])
    out = controller(script, clock=lambda: float(next(ticks))).run(
        base_plan(), query("explain rate limiting for payments api"), top_k=5)
    assert out.report.stop_reason == StopReason.DEADLINE_EXCEEDED and out.report.rounds_executed == 1


def test_error_in_later_round_keeps_earlier_evidence():
    script = Script([cand("c1", "auth")], RuntimeError("vector store down"))
    out = controller(script).run(base_plan(), query("explain rate limiting for payments api"), top_k=5)
    assert out.report.stop_reason == StopReason.EXECUTION_ERROR
    assert [ve.candidate.provenance.chunk_id for ve in out.evidence] == ["c1"]


def test_error_in_first_round_propagates_to_the_caller():
    script = Script(RuntimeError("vector store down"))
    try:
        controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    except RuntimeError:
        return
    raise AssertionError("round 0 errors must reach the caller")


def test_missing_capability_falls_back_to_next_action():
    script = Script([], [cand("c1", "ContextAPI a"), cand("c2", "ContextAPI b"), cand("c3", "ContextAPI c")])
    out = controller(script, reg=registry(semantic=False, lexical=False)).run(
        base_plan(), query("what is contextapi"), top_k=5)
    assert out.report.rounds[1].action == EscalationAction.KEYWORD_REWRITE
    assert [s.capability_id for s in script.plans[1].graph.steps] == ["cap_hybrid"]


def test_degraded_execution_is_reported_as_a_gap():
    script = Script([], failed_rounds=(0,))
    out = controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    first_round = out.report.rounds[0].gap_types   # later rounds ran fine, so look at round 0
    assert GapType.NO_EVIDENCE in first_round and GapType.EXECUTION_DEGRADED in first_round
    assert out.report.rounds[1].action == EscalationAction.SPLIT_RETRIEVERS


def test_report_is_json_ready():
    script = Script([cand("c1", "ContextAPI a"), cand("c2", "ContextAPI b")])
    out = controller(script).run(base_plan(), query("what is contextapi"), top_k=5)
    import json
    json.dumps(out.report.model_dump(mode="json"))

# ---------------------------------------------------------- production fixes

def test_crashed_hard_gap_check_never_yields_sufficient():
    from app.retrieval.sufficiency.service import default_evaluators

    class Broken:
        name = SignalName.TERM_COVERAGE

        def evaluate(self, inp):
            raise RuntimeError("boom")

    cfg = SufficiencyConfig()
    evaluators = [Broken()] + [e for e in default_evaluators(cfg) if e.name != SignalName.TERM_COVERAGE]
    cands = [cand("c1", "ContextAPI is a platform"), cand("c2", "ContextAPI docs"), cand("c3", "ContextAPI usage")]
    validated = accept_all(CandidateEvidenceSet(plan_id="P", status=ExecutionStatus.SUCCESS, candidates=tuple(cands)))
    plan = base_plan()
    inp = AssessmentInput(
        query=query("what is contextapi"), accepted=validated.validated_evidence,
        all_validated=validated.validated_evidence, latest_round=round_result(plan, cands),
        round_index=0, top_k=5,
    )
    a = SufficiencyService(cfg, evaluators=evaluators).assess(inp)
    assert a.verdict != SufficiencyVerdict.SUFFICIENT
    assert any(g.details.get("evaluator_error") for g in a.gaps)


def test_search_deeper_never_exceeds_profile_max_top_k():
    from app.retrieval.sufficiency.escalation import EscalationState
    planner = EscalationPlanner(SufficiencyConfig(max_top_k=20), registry())
    gap = mock.Mock(gap_type=GapType.TOO_FEW_EVIDENCE, details={})
    decision = planner._build(
        EscalationAction.WIDEN_DEPTH, gap, query("what is contextapi"),
        EscalationState(current_top_k=15), 5, 3,
    )
    assert decision is not None and decision.top_k == 20
