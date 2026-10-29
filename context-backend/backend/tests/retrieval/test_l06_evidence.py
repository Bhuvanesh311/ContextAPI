"""
Unit tests for L06 (Evidence Intelligence & Validation).

No database, no ChromaDB, no network. Run from the backend folder:

    python -m pytest tests/retrieval/test_l06_evidence.py -v
"""
from app.retrieval.engine.enums import ExecutionStatus, OperatorType
from app.retrieval.engine.schemas import CandidateEvidence, CandidateEvidenceSet, ProvenanceMetadata
from app.retrieval.evidence.enums import EvidenceState
from app.retrieval.evidence.evaluators.deterministic import DeterministicValidator
from app.retrieval.evidence.evaluators.integrity import (
    AuthorityFreshnessEvaluator,
    ProvenanceEvaluator,
    QualityEvaluator,
    RelevanceEvaluator,
    ScopeDefenseEvaluator,
)
from app.retrieval.evidence.evaluators.pairwise import TokenJaccardPairwiseEvaluator
from app.retrieval.evidence.evaluators.similarity import SimilarityEvaluator
from app.retrieval.evidence.models import RelationshipType
from app.retrieval.evidence.package import build_evidence_package
from app.retrieval.evidence.policy import EvidencePolicy
from app.retrieval.evidence.service import EvidenceIntelligenceConfig, EvidenceIntelligenceService
from app.retrieval.sufficiency.enums import StopReason
from app.retrieval.sufficiency.models import SufficiencyReport

ALLOWED = {"V1", "V2"}


def info(**overrides):
    base = {"name": "a.pdf", "document_active": True, "is_current": True, "updated_at": None}
    base.update(overrides)
    return base


def cand(chunk_id, content, version="V1", doc="DOC1", matched_by="lexical+semantic", score=0.03):
    prov = ProvenanceMetadata(
        document_id=doc, document_version_id=version, chunk_id=chunk_id,
        source_type="postgres", step_id="s", operator_type=OperatorType.SEMANTIC,
    )
    meta = {"matched_by": matched_by} if matched_by else {}
    return CandidateEvidence(content=content, provenance=prov, score=score, retrieval_metadata=meta)


def run(cands, query="request timeout", version_info=None, allowed=ALLOWED):
    evaluators = [
        DeterministicValidator(), ScopeDefenseEvaluator(), ProvenanceEvaluator(), QualityEvaluator(),
        AuthorityFreshnessEvaluator(), SimilarityEvaluator(), RelevanceEvaluator(),
    ]
    service = EvidenceIntelligenceService(
        evaluators=evaluators,
        policy=EvidencePolicy(),
        config=EvidenceIntelligenceConfig(
            max_evaluator_calls_per_candidate=len(evaluators), exact_deduplication_only=False,
        ),
        semantic_evaluator=TokenJaccardPairwiseEvaluator(),
    )
    if version_info is None:
        version_info = {"V1": info(), "V2": info()}
    candidate_set = CandidateEvidenceSet(plan_id="P", status=ExecutionStatus.SUCCESS, candidates=tuple(cands))
    return service.process(
        candidate_set,
        context={"required_scope": {}, "allowed_version_ids": allowed,
                 "version_info": version_info, "query": query},
    )


def states(validated):
    return {ve.candidate.provenance.chunk_id: ve.state for ve in validated.validated_evidence}


def by_chunk(validated, chunk_id):
    return next(ve for ve in validated.validated_evidence if ve.candidate.provenance.chunk_id == chunk_id)


TIMEOUT_30 = "The default request timeout is 30 seconds for every client application."
TIMEOUT_60 = "The default request timeout is 60 seconds for every client application."
CONTEXTAPI = "ContextAPI is an API reverse engineering system that combines runtime exploration with agentic retrieval augmented generation."


def test_clean_evidence_is_accepted():
    v = run([cand("C1", TIMEOUT_30)])
    assert states(v) == {"C1": EvidenceState.ACCEPTED}


def test_chunk_outside_l02_scope_is_invalid():
    v = run([cand("C1", TIMEOUT_30, version="V9")])
    ve = by_chunk(v, "C1")
    assert ve.state == EvidenceState.INVALID
    assert "outside" in ve.primary_reason


def test_unresolved_document_is_invalid():
    v = run([cand("C1", TIMEOUT_30, doc="doc-unknown")])
    ve = by_chunk(v, "C1")
    assert ve.state == EvidenceState.INVALID
    assert "Document" in ve.primary_reason


def test_empty_or_garbage_content_is_rejected():
    v = run([cand("C1", "too short"), cand("C2", "!!! ??? ### 1234 ### ??? !!! 5678 ### ??? !!!")])
    assert states(v) == {"C1": EvidenceState.REJECTED, "C2": EvidenceState.REJECTED}


def test_indented_table_rows_are_usable_text():
    # CSV rows are chunked as indented JSON: lots of whitespace, quotes and
    # digits. They were rejected as "mostly non-text" and never answered.
    rows = '[\n    {\n        "sku": "A200",\n        "item": "copper wire",\n        "stock": "320"\n    },\n' \
           '    {\n        "sku": "B300",\n        "item": "safety gloves",\n        "stock": "75"\n    }\n]'
    v = run([cand("C1", rows)], query="copper wire stock")
    assert by_chunk(v, "C1").state == EvidenceState.ACCEPTED


def test_keyword_only_hit_without_question_terms_is_rejected():
    weather = "The weather is sunny today in the park near the lake with many people."
    v = run([cand("C1", weather, matched_by="lexical")], query="rate limiting policy")
    assert by_chunk(v, "C1").state == EvidenceState.REJECTED


def test_semantic_match_without_question_terms_is_kept():
    text = "Callers may only send a limited number of calls before the service slows them down."
    v = run([cand("C1", text, matched_by="semantic")], query="rate limiting policy")
    assert by_chunk(v, "C1").state == EvidenceState.ACCEPTED


def test_superseded_or_inactive_document_is_rejected():
    v = run([cand("C1", TIMEOUT_30)], version_info={"V1": info(is_current=False), "V2": info()})
    assert by_chunk(v, "C1").state == EvidenceState.REJECTED
    v = run([cand("C1", TIMEOUT_30)], version_info={"V1": info(document_active=False), "V2": info()})
    assert by_chunk(v, "C1").state == EvidenceState.REJECTED


def test_near_duplicate_is_marked_duplicate():
    v = run([cand("C1", CONTEXTAPI), cand("C2", CONTEXTAPI + " Extra.")], query="ContextAPI")
    s = states(v)
    assert s["C1"] == EvidenceState.ACCEPTED
    assert s["C2"] == EvidenceState.DUPLICATE
    assert by_chunk(v, "C2").relationships[0].relation_type == RelationshipType.DUPLICATES


def test_contradicting_numbers_are_flagged_and_linked():
    v = run([cand("C1", TIMEOUT_30), cand("C2", TIMEOUT_60, doc="DOC2", version="V2")])
    first, second = by_chunk(v, "C1"), by_chunk(v, "C2")
    assert first.state == EvidenceState.ACCEPTED          # better-ranked side stays
    assert second.state == EvidenceState.CONFLICTING
    assert first.relationships[0].relation_type == RelationshipType.CONTRADICTS
    assert second.relationships[0].relation_type == RelationshipType.CONTRADICTS


def test_overlapping_neighbour_chunks_are_not_a_conflict():
    a = "Exploration continues until successive iterations produce minimal new information."
    b = a + " Using the validated knowledge base, the system generates OpenAPI specifications."
    v = run([cand("C1", a), cand("C2", b)], query="exploration iterations")
    assert EvidenceState.CONFLICTING not in states(v).values()


def test_evidence_package_lists_both_sides_of_a_conflict():
    v = run([cand("C1", TIMEOUT_30), cand("C2", TIMEOUT_60, doc="DOC2", version="V2")])
    accepted = [ve for ve in v.validated_evidence if ve.state == EvidenceState.ACCEPTED]
    report = SufficiencyReport.empty(StopReason.NO_SEARCHABLE_DOCUMENTS, "test")
    pkg = build_evidence_package(
        request_id="R1", query="request timeout", profile="STANDARD", final_evidence=accepted,
        report=report, last_validated=v, document_names={"DOC1": "a.pdf", "DOC2": "b.pdf"},
        documents_in_scope=2,
    )
    assert len(pkg.conflicts) == 1
    assert sorted(pkg.conflicts[0].chunk_ids) == ["C1", "C2"]
    assert pkg.excluded == {"CONFLICTING": 1}
    assert pkg.evidence[0].source.document_name == "a.pdf"
    assert any("conflict" in w for w in pkg.warnings)

# ---------------------------------------------------------------- production fixes

def test_profile_candidate_cap_and_every_dropped_candidate_is_counted():
    from datetime import datetime
    cands = [cand(f"c{i}", f"request timeout setting number {i} explained in detail") for i in range(6)]
    service_ctx = {"required_scope": {}, "allowed_version_ids": ALLOWED,
                   "version_info": {"V1": info(), "V2": info()}, "query": "request timeout",
                   "max_candidates": 4}
    evaluators = [DeterministicValidator(), ScopeDefenseEvaluator()]
    service = EvidenceIntelligenceService(evaluators=evaluators, policy=EvidencePolicy(),
                                          config=EvidenceIntelligenceConfig(max_candidates=50))
    out = service.process(CandidateEvidenceSet(plan_id="P", status=ExecutionStatus.SUCCESS,
                                               candidates=tuple(cands)), context=service_ctx)
    assert len(out.validated_evidence) <= 4
    assert out.unevaluated_count == 6 - len(out.validated_evidence) >= 2


def test_statements_about_different_subjects_do_not_conflict():
    from app.retrieval.evidence.contradiction import find_contradiction
    a = "The free plan rate limit for the public search endpoint is 100 requests per minute per key."
    b = "The pro plan rate limit for the public search endpoint is 1000 requests per minute per key."
    assert find_contradiction(a, b) is None


def test_same_statement_with_different_numbers_still_conflicts():
    from app.retrieval.evidence.contradiction import find_contradiction
    a = "The rate limit for the public search endpoint is 100 requests per minute per key."
    b = "The rate limit for the public search endpoint is 1000 requests per minute per key."
    assert find_contradiction(a, b)


def test_newer_document_wins_a_conflict():
    from datetime import datetime
    old = "The rate limit for the public search endpoint is 100 requests per minute per key."
    new = "The rate limit for the public search endpoint is 1000 requests per minute per key."
    out = run(
        [cand("c_old", old, version="V1", doc="DOC1"), cand("c_new", new, version="V2", doc="DOC2")],
        query="public search endpoint rate limit",
        version_info={"V1": info(updated_at=datetime(2025, 1, 1)), "V2": info(updated_at=datetime(2026, 6, 1))},
    )
    s = states(out)
    assert s["c_new"] == EvidenceState.ACCEPTED
    assert s["c_old"] == EvidenceState.CONFLICTING
