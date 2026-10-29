from types import SimpleNamespace

from app.core.enums import RetrievalRequestStatus as S
from app.retrieval.router import _NOTICES, _relevance


def _req(status=S.COMPLETED, results=({"rank": 1},), verdict="SUFFICIENT", stop_reason="SUFFICIENT"):
    return SimpleNamespace(
        status=status, results=list(results),
        sufficiency={"verdict": verdict, "stop_reason": stop_reason},
    )


def test_sufficient_evidence_is_relevant_without_notice():
    assert _relevance(_req(), {"status": "SUCCESS"}) == ("relevant", None)


def test_insufficient_verdict_is_not_relevant_even_without_generation():
    # FAST / STANDARD never generate, but must still tell the user.
    assert _relevance(_req(verdict="INSUFFICIENT"), {}) == ("not_relevant", _NOTICES["not_relevant"])


def test_model_abstaining_is_not_relevant():
    generated = {"status": "INSUFFICIENT_CONTEXT", "answer": "The documents do not contain this."}
    assert _relevance(_req(), generated)[0] == "not_relevant"


def test_no_results_is_not_relevant():
    assert _relevance(_req(results=[]), {})[0] == "not_relevant"


def test_partial_verdict_or_answer_is_partial():
    assert _relevance(_req(verdict="PARTIALLY_SUFFICIENT"), {})[0] == "partial"
    assert _relevance(_req(), {"status": "PARTIAL"})[0] == "partial"


def test_project_without_documents():
    req = _req(results=[], verdict="INSUFFICIENT", stop_reason="NO_SEARCHABLE_DOCUMENTS")
    assert _relevance(req, {}) == ("no_documents", _NOTICES["no_documents"])


def test_failures_and_running_requests_have_no_relevance():
    assert _relevance(_req(status=S.RUNNING), {}) == (None, None)
    assert _relevance(_req(status=S.FAILED), {}) == (None, None)
    assert _relevance(_req(), {"status": "FAILED"}) == (None, None)
