from types import SimpleNamespace

from app.core.enums import RetrievalRequestStatus as S
from app.retrieval.router import _answer_warnings


def _req(status=S.COMPLETED, results=None, sufficiency=None):
    return SimpleNamespace(status=status, results=results, sufficiency=sufficiency)


def test_no_documents_explains_why_answer_is_empty():
    req = _req(results=[], sufficiency={"gaps": [{"message": "No active documents match this request's project and constraints."}]})

    warnings = _answer_warnings(req, {})

    assert "No active documents match this request's project and constraints." in warnings
    assert "No matching text was found in this project's documents." in warnings


def test_skipped_generation_reports_skip_reason():
    generated = {"skip_reason": "Retrieved evidence is not sufficient to answer; no model was called.", "warnings": []}

    warnings = _answer_warnings(_req(results=[{"rank": 1}]), generated)

    assert warnings == ["Retrieved evidence is not sufficient to answer; no model was called."]


def test_answered_request_keeps_only_model_warnings():
    generated = {"answer": "Python is a language [1].", "warnings": ["Context was truncated to fit the budget."]}

    assert _answer_warnings(_req(results=[{"rank": 1}]), generated) == ["Context was truncated to fit the budget."]


def test_unfinished_request_has_no_explanation_yet():
    assert _answer_warnings(_req(status=S.RUNNING), {}) == []
