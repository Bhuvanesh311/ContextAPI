"""Per-call timeouts (call_with_timeout / budgeted_timeout) and their fallbacks."""

import time
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.retrieval.engine import reranker as reranker_mod
from app.retrieval.engine.operators.semantic import SemanticOperator
from app.retrieval.engine.reranker import BGEReranker
from app.retrieval.engine.timeouts import CallTimeoutError, budgeted_timeout, call_with_timeout

from tests.retrieval.test_l05_engine import _candidate


# ---------------------------------------------------------------- call_with_timeout

def test_call_with_timeout_returns_result():
    assert call_with_timeout(lambda a, b: a + b, 1.0, 2, 3) == 5


def test_call_with_timeout_stops_waiting_on_slow_call():
    start = time.monotonic()
    with pytest.raises(CallTimeoutError):
        call_with_timeout(time.sleep, 0.05, 1.0)
    assert time.monotonic() - start < 0.5


def test_call_with_timeout_propagates_errors():
    def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError, match="bad"):
        call_with_timeout(boom, 1.0)


# ---------------------------------------------------------------- budgeted_timeout

def test_budgeted_timeout_without_deadline_uses_setting():
    assert budgeted_timeout(30, None) == 30


def test_budgeted_timeout_far_deadline_uses_setting():
    assert budgeted_timeout(5, time.monotonic() + 100) == 5


def test_budgeted_timeout_capped_by_remaining_budget():
    # FAST profile: 8 s budget must win over a 30 s embed setting.
    assert budgeted_timeout(30, time.monotonic() + 8) <= 8


def test_budgeted_timeout_past_deadline_raises():
    with pytest.raises(CallTimeoutError):
        budgeted_timeout(30, time.monotonic() - 1)


# ---------------------------------------------------------------- reranker fallback

class _Model:
    def __init__(self, scores=None, delay=0.0):
        self.scores, self.delay, self.calls = scores, delay, 0

    def predict(self, pairs):
        self.calls += 1
        time.sleep(self.delay)
        return self.scores or [0.0] * len(pairs)


def _cands():
    return [_candidate("C1", "alpha", 0.9), _candidate("C2", "beta", 0.5), _candidate("C3", "gamma", 0.1)]


def test_reranker_timeout_keeps_original_order(monkeypatch):
    monkeypatch.setattr(reranker_mod, "_load_model", lambda name: _Model(delay=1.0))
    monkeypatch.setattr(settings, "RETRIEVAL_RERANK_TIMEOUT_SECONDS", 0.05)
    cands = _cands()
    start = time.monotonic()
    out = BGEReranker().rerank("q", cands)
    assert [c.provenance.chunk_id for c in out] == ["C1", "C2", "C3"]
    assert time.monotonic() - start < 0.5


def test_reranker_past_deadline_skips_predict(monkeypatch):
    model = _Model()
    monkeypatch.setattr(reranker_mod, "_load_model", lambda name: model)
    out = BGEReranker().rerank("q", _cands(), deadline=time.monotonic() - 1)
    assert [c.provenance.chunk_id for c in out] == ["C1", "C2", "C3"]
    assert model.calls == 0


def test_reranker_success_reorders_by_model_score(monkeypatch):
    monkeypatch.setattr(reranker_mod, "_load_model", lambda name: _Model(scores=[0.1, 0.2, 3.0]))
    out = BGEReranker().rerank("q", _cands(), deadline=time.monotonic() + 10)
    assert [c.provenance.chunk_id for c in out] == ["C3", "C2", "C1"]


# ---------------------------------------------------------------- semantic operator

class _SlowEmbedder:
    def embed_query(self, req):
        time.sleep(1.0)


def test_semantic_operator_embed_is_capped_by_request_deadline(monkeypatch):
    monkeypatch.setattr(settings, "RETRIEVAL_EMBED_TIMEOUT_SECONDS", 30)
    op = SemanticOperator(embedding_adapter=_SlowEmbedder(), vector_adapter=None)
    step = SimpleNamespace(query_binding=SimpleNamespace(query_text="q"), step_scope={}, step_id="s1")
    start = time.monotonic()
    with pytest.raises(CallTimeoutError):
        op.execute(step, {"top_k": 5, "deadline": time.monotonic() + 0.05})
    assert time.monotonic() - start < 0.5
