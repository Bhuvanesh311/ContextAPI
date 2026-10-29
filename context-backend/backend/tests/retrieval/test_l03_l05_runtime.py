"""L03 time budget / entities and L05 hybrid parallelism, scope, tracing, embedding cache."""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.retrieval.engine.exceptions import ScopeViolationError
from app.retrieval.engine.operators.hybrid import HybridOperator
from app.retrieval.engine.operators.semantic import SemanticOperator
from app.retrieval.intelligence.object import analyze_objects
from app.retrieval.intelligence.providers.router import ModelProviderRouter


# ---------------------------------------------------------------- L03

def test_tier_c_providers_share_one_deadline():
    router = ModelProviderRouter.__new__(ModelProviderRouter)
    router._provider_order = ["a", "b", "c"]
    router._cooldowns = {}
    router.COOLDOWN_SECONDS = 60
    calls = []

    def slow(prompt, schema, timeout):
        calls.append(timeout)
        time.sleep(0.6)
        raise RuntimeError("down")

    router.tier_c_providers = {n: SimpleNamespace(generate_structured=slow) for n in "abc"}
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="time budget exhausted"):
        router.execute_tier_c("p", {}, timeout=30, deadline=time.monotonic() + 1.5)
    assert time.monotonic() - start < 2.0
    assert all(t <= 1 for t in calls) and len(calls) < 3


def test_entities_extracted_deterministically():
    r = analyze_objects("What does POST /api/v1/users return on a 401 error with `max_retries` set?")
    assert "POST /api/v1/users" in r.entities
    assert "HTTP 401" in r.entities
    assert "max_retries" in r.entities
    assert analyze_objects("what is the refund policy").entities == []


def test_prefixed_ids_are_identifiers():
    assert analyze_objects("status of PROJ000007").identifiers == ["PROJ000007"]


# ---------------------------------------------------------------- L05 hybrid

class _Op:
    def __init__(self, delay=0.0, raises=None, results=None):
        self.delay, self.raises, self.results = delay, raises, results or []

    def execute(self, step, context_data):
        time.sleep(self.delay)
        if self.raises:
            raise self.raises
        return self.results


def _hybrid(semantic, lexical):
    op = HybridOperator(semantic, lexical, session=MagicMock())
    op._fuse = lambda step_id, s, l, k: (s, l)
    return op


STEP = SimpleNamespace(step_id="s1")


def test_hybrid_runs_semantic_and_lexical_in_parallel():
    op = _hybrid(_Op(delay=0.4, results=["sem"]), _Op(delay=0.4, results=["lex"]))
    start = time.monotonic()
    assert op.execute(STEP, {"top_k": 5}) == (["sem"], ["lex"])
    assert time.monotonic() - start < 0.7


def test_hybrid_one_side_failing_still_answers():
    op = _hybrid(_Op(raises=RuntimeError("chroma down")), _Op(results=["lex"]))
    assert op.execute(STEP, {"top_k": 5}) == ([], ["lex"])


@pytest.mark.parametrize("which", ["semantic", "lexical"])
def test_hybrid_scope_violation_is_not_swallowed(which):
    bad, ok = _Op(raises=ScopeViolationError("no scope")), _Op(results=["x"])
    op = _hybrid(bad, ok) if which == "semantic" else _hybrid(ok, bad)
    with pytest.raises(ScopeViolationError):
        op.execute(STEP, {"top_k": 5})


# ---------------------------------------------------------------- L05 misc

def test_structured_capability_traced_as_structured():
    from app.retrieval.engine.enums import OperatorType
    from app.retrieval.engine.executor import _operator_type_for
    assert _operator_type_for("cap_structured") == OperatorType.STRUCTURED


def test_query_is_embedded_once_across_steps():
    embedder = MagicMock()
    embedder.embed_query.return_value = SimpleNamespace(embedding=[0.1, 0.2])
    vector = MagicMock()
    vector.search.return_value = []
    op = SemanticOperator(embedding_adapter=embedder, vector_adapter=vector)
    step = SimpleNamespace(query_binding=SimpleNamespace(query_text="rate limit"),
                           step_scope={"document_version_id": {"$in": ["V1"]}}, step_id="s1")
    for _ in range(3):
        op.execute(step, {"top_k": 5})
    assert embedder.embed_query.call_count == 1
    assert vector.search.call_count == 3
