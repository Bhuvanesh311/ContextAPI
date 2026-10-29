"""L5 must never run a search without the L02 document scope."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.retrieval.engine.adapters.lexical_store import LexicalSearchRequest, PostgresLexicalStoreAdapter
from app.retrieval.engine.adapters.structured_store import PostgresStructuredStoreAdapter, StructuredSearchRequest
from app.retrieval.engine.adapters.vector_store import ChromaVectorStoreAdapter, VectorSearchRequest
from app.retrieval.engine.exceptions import ScopeViolationError
from app.retrieval.engine.scope_guard import require_version_scope
from app.retrieval.planning.schemas import _freeze_dict

SCOPE = {"document_version_id": {"$in": ["V1", "V2"]}}
UNSCOPED = [None, {}, {"document_version_id": {}}, {"document_version_id": {"$in": []}}, {"project_id": "P1"}]


@pytest.mark.parametrize("filters", UNSCOPED)
def test_guard_rejects_missing_scope(filters):
    with pytest.raises(ScopeViolationError):
        require_version_scope(filters)


def test_guard_accepts_planner_frozen_scope():
    assert require_version_scope(_freeze_dict(SCOPE)) == ["V1", "V2"]


@pytest.mark.parametrize("filters", UNSCOPED[1:])
def test_lexical_adapter_refuses_unscoped_search(filters):
    session = MagicMock()
    with pytest.raises(ScopeViolationError):
        PostgresLexicalStoreAdapter(session).search(
            LexicalSearchRequest(query_text="refund policy", top_k=5, filters=filters), "s1"
        )
    session.query.assert_not_called()


@pytest.mark.parametrize("filters", UNSCOPED[1:])
def test_structured_adapter_refuses_unscoped_search(filters):
    session = MagicMock()
    with pytest.raises(ScopeViolationError):
        PostgresStructuredStoreAdapter(session).search(
            StructuredSearchRequest(query_text='"refund policy"', top_k=5, filters=filters), "s1"
        )
    session.query.assert_not_called()


@pytest.mark.parametrize("filters", UNSCOPED[1:])
def test_vector_adapter_refuses_unscoped_search(filters):
    adapter = ChromaVectorStoreAdapter.__new__(ChromaVectorStoreAdapter)
    adapter.collection = MagicMock()
    with pytest.raises(ScopeViolationError):
        adapter.search(VectorSearchRequest(embedding=[0.1], top_k=5, filters=filters), "s1")
    adapter.collection.query.assert_not_called()


def test_executor_does_not_fall_back_after_scope_violation():
    from app.retrieval.engine.executor import EngineExecutor
    from tests.retrieval.test_l05_engine import OkOperator

    class Unscoped(OkOperator):
        def execute(self, step, context_data):
            raise ScopeViolationError("no scope")

    fallback = OkOperator("cap_semantic")
    fallback.execute = MagicMock(return_value=[])
    executor = EngineExecutor(operators=[Unscoped("cap_hybrid"), fallback], resolver=MagicMock())
    plan = SimpleNamespace(
        execution_limits=SimpleNamespace(max_steps=5, max_latency_ms=10_000),
        graph=SimpleNamespace(steps=(SimpleNamespace(step_id="s1", capability_id="cap_hybrid", depends_on=()),)),
        fallback_policy=SimpleNamespace(fallback_capabilities=("cap_semantic",), max_attempts=1),
        plan_id="p1",
        request_id="r1",
    )
    with pytest.raises(ScopeViolationError):
        executor.execute_plan(plan)
    fallback.execute.assert_not_called()
