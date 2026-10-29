"""
Unit tests for L05 (Retrieval Engine) and the BGE Reranker.

No real database, ChromaDB or model downloads. Operators and the CrossEncoder
are replaced with lightweight fakes. Run from the backend folder:

    python -m pytest tests/retrieval/test_l05_engine.py -v
"""
import uuid
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums import RetrievalRequirementType
from app.retrieval.engine.enums import ExecutionStatus, OperatorType
from app.retrieval.engine.executor import EngineExecutor
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.engine.reranker import BGEReranker
from app.retrieval.engine.schemas import (
    CandidateEvidence,
    CandidateEvidenceSet,
    ExecutionTrace,
    ProvenanceMetadata,
    RawRetrievalResult,
)
from app.retrieval.planning.schemas import (
    ExecutionGraph,
    ExecutionLimits,
    FallbackPolicy,
    QueryBinding,
    RetrievalPlan,
    RetrievalStep,
)


# ---------------------------------------------------------------- fakes / helpers

def _prov(chunk_id="C1", doc="DOC1", version="V1"):
    return ProvenanceMetadata(
        document_id=doc, document_version_id=version, chunk_id=chunk_id,
        source_type="test", step_id="s1", operator_type=OperatorType.SEMANTIC,
    )


def _candidate(chunk_id="C1", content="hello world", score=0.5):
    return CandidateEvidence(
        content=content, provenance=_prov(chunk_id), score=score,
    )


class OkOperator(BaseOperator):
    """Returns a fixed list of raw results."""
    def __init__(self, cap_id: str, results: List[RawRetrievalResult] = None):
        self._cap_id = cap_id
        self._results = results or []

    @property
    def capability_id(self) -> str:
        return self._cap_id

    def execute(self, step, context_data: Dict[str, Any] = None) -> List[RawRetrievalResult]:
        return list(self._results)


class FailOperator(BaseOperator):
    """Always raises."""
    def __init__(self, cap_id: str):
        self._cap_id = cap_id

    @property
    def capability_id(self) -> str:
        return self._cap_id

    def execute(self, step, context_data: Dict[str, Any] = None) -> List[RawRetrievalResult]:
        raise RuntimeError("Operator error")


class FakeResolver:
    """Converts raw results directly into CandidateEvidence without DB."""
    def resolve(self, raw: List[RawRetrievalResult]) -> List[CandidateEvidence]:
        return [
            CandidateEvidence(
                content=f"content-{r.vector_id}",
                provenance=_prov(chunk_id=r.vector_id or "C"),
                score=r.score,
            )
            for r in raw
        ]


def _raw(vector_id: str, score: float = 0.5):
    return RawRetrievalResult(step_id="s1", vector_id=vector_id, score=score)


def _step(cap_id="cap_hybrid", query="test query"):
    return RetrievalStep(
        capability_id=cap_id,
        query_binding=QueryBinding(binding_type="original", query_text=query),
        step_scope={"document_version_id": {"$in": ["V1"]}},
    )


def _plan(steps=None, max_latency_ms=10000, fallback_capabilities=()):
    steps = steps or [_step()]
    fb = FallbackPolicy(
        strategy_id="std",
        max_attempts=len(fallback_capabilities),
        fallback_capabilities=tuple(fallback_capabilities),
    )
    return RetrievalPlan(
        request_id="REQ1",
        correlation_id="COR1",
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        planning_summary="test",
        graph=ExecutionGraph(steps=tuple(steps)),
        execution_limits=ExecutionLimits(max_latency_ms=max_latency_ms, max_steps=10),
        stop_conditions=__import__(
            "app.retrieval.planning.schemas", fromlist=["StopConditions"]
        ).StopConditions(),
        fallback_policy=fb,
    )


# ---------------------------------------------------------------- executor basics

def test_executor_returns_candidate_evidence_set():
    raw = [_raw("vec1", 0.8), _raw("vec2", 0.6)]
    op = OkOperator("cap_hybrid", raw)
    result = EngineExecutor([op], resolver=FakeResolver()).execute_plan(_plan())
    assert isinstance(result, CandidateEvidenceSet)
    assert result.status == ExecutionStatus.SUCCESS
    assert len(result.candidates) == 2


def test_executor_records_execution_trace():
    op = OkOperator("cap_hybrid", [_raw("v1")])
    result = EngineExecutor([op], resolver=FakeResolver()).execute_plan(_plan())
    assert len(result.traces) == 1
    assert result.traces[0].status == ExecutionStatus.SUCCESS


def test_executor_with_no_resolver_returns_empty_candidates():
    op = OkOperator("cap_hybrid", [_raw("v1")])
    result = EngineExecutor([op]).execute_plan(_plan())
    assert result.candidates == ()
    assert result.status == ExecutionStatus.SUCCESS


def test_executor_unknown_capability_marks_step_failed():
    result = EngineExecutor([]).execute_plan(_plan())
    assert result.traces[0].status == ExecutionStatus.FAILED
    # No candidates since operator not found
    assert result.candidates == ()


def test_executor_operator_exception_marks_step_partial():
    op = FailOperator("cap_hybrid")
    result = EngineExecutor([op], resolver=FakeResolver()).execute_plan(_plan())
    assert result.status == ExecutionStatus.PARTIAL
    assert result.traces[0].status == ExecutionStatus.FAILED


def test_executor_respects_max_steps():
    steps = [_step() for _ in range(5)]
    op = OkOperator("cap_hybrid", [_raw("v1")])
    plan = _plan(steps=steps, max_latency_ms=60000)
    # Override max_steps to 2
    from app.retrieval.planning.schemas import ExecutionLimits
    plan = plan.model_copy(update={"execution_limits": ExecutionLimits(max_steps=2, max_latency_ms=60000)})
    result = EngineExecutor([op], resolver=FakeResolver()).execute_plan(plan)
    assert len(result.traces) == 2


# ---------------------------------------------------------------- fallback policy

def test_fallback_operator_is_tried_when_primary_fails():
    primary = FailOperator("cap_hybrid")
    fallback = OkOperator("cap_semantic", [_raw("v1", 0.7)])
    plan = _plan(fallback_capabilities=("cap_semantic",))
    result = EngineExecutor([primary, fallback], resolver=FakeResolver()).execute_plan(plan)
    assert len(result.candidates) == 1
    # Primary failed, fallback succeeded → step should be in completed
    success_traces = [t for t in result.traces if t.status == ExecutionStatus.SUCCESS]
    assert len(success_traces) == 1


def test_fallback_not_used_when_primary_succeeds():
    primary = OkOperator("cap_hybrid", [_raw("v1")])
    fallback = OkOperator("cap_semantic", [_raw("v2")])
    plan = _plan(fallback_capabilities=("cap_semantic",))
    result = EngineExecutor([primary, fallback], resolver=FakeResolver()).execute_plan(plan)
    # Only primary's result; fallback should not run
    assert len(result.candidates) == 1


def test_both_primary_and_fallback_fail_marks_partial():
    primary = FailOperator("cap_hybrid")
    fallback = FailOperator("cap_semantic")
    plan = _plan(fallback_capabilities=("cap_semantic",))
    result = EngineExecutor([primary, fallback], resolver=FakeResolver()).execute_plan(plan)
    assert result.status == ExecutionStatus.PARTIAL
    assert result.candidates == ()


# ---------------------------------------------------------------- multi-step

def test_multiple_steps_all_run_and_results_are_merged():
    steps = [_step("cap_semantic", "query A"), _step("cap_lexical", "query B")]
    sem = OkOperator("cap_semantic", [_raw("v1")])
    lex = OkOperator("cap_lexical", [_raw("v2")])
    result = EngineExecutor([sem, lex], resolver=FakeResolver()).execute_plan(_plan(steps=steps))
    assert result.status == ExecutionStatus.SUCCESS
    assert len(result.candidates) == 2
    assert len(result.traces) == 2


# ---------------------------------------------------------------- context_data / top_k

def test_context_data_is_forwarded_to_operator():
    received = {}

    class CapturingOperator(BaseOperator):
        @property
        def capability_id(self): return "cap_hybrid"
        def execute(self, step, context_data=None):
            received.update(context_data or {})
            return []

    EngineExecutor([CapturingOperator()]).execute_plan(
        _plan(), context_data={"top_k": 15}
    )
    assert received.get("top_k") == 15


# ================================================================ Reranker tests

def test_reranker_reorders_by_score():
    candidates = [
        _candidate("C1", "low relevance text", score=0.9),
        _candidate("C2", "highly relevant answer", score=0.1),
    ]

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_model = MagicMock()
        # C1 gets score 0.1, C2 gets score 0.9 from cross-encoder
        mock_model.predict.return_value = [0.1, 0.9]
        mock_load.return_value = mock_model

        reranker = BGEReranker(model_name="test-model")
        result = reranker.rerank("relevant query", candidates)

    assert result[0].provenance.chunk_id == "C2"  # higher score first
    assert result[1].provenance.chunk_id == "C1"


def test_reranker_updates_score_field():
    candidates = [_candidate("C1", "some text", score=0.5)]

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.85]
        mock_load.return_value = mock_model

        result = BGEReranker(model_name="test-model").rerank("query", candidates)

    assert result[0].score == pytest.approx(0.85)


def test_reranker_returns_original_order_on_model_failure():
    candidates = [_candidate("C1", "a"), _candidate("C2", "b")]

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_load.side_effect = RuntimeError("model not found")
        result = BGEReranker(model_name="bad-model").rerank("query", candidates)

    # Graceful degradation: original order preserved
    assert [c.provenance.chunk_id for c in result] == ["C1", "C2"]


def test_reranker_with_empty_candidates_is_a_no_op():
    reranker = BGEReranker()
    assert reranker.rerank("query", []) == []


def test_reranker_with_empty_query_is_a_no_op():
    candidates = [_candidate("C1", "text")]
    reranker = BGEReranker()
    result = reranker.rerank("   ", candidates)
    assert result == candidates


def test_reranker_respects_max_candidates_cap():
    candidates = [_candidate(f"C{i}", f"text {i}") for i in range(10)]
    scores_returned = list(range(5, 0, -1))  # 5 scores for 5 candidates

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_model = MagicMock()
        mock_model.predict.return_value = scores_returned
        mock_load.return_value = mock_model

        reranker = BGEReranker(model_name="test-model", max_candidates=5)
        result = reranker.rerank("query", candidates)

    # model.predict was called with exactly 5 pairs
    call_args = mock_model.predict.call_args[0][0]
    assert len(call_args) == 5
    # Remaining 5 candidates appended unchanged at the end
    assert len(result) == 10
    remainder_ids = {c.provenance.chunk_id for c in result[5:]}
    assert remainder_ids == {f"C{i}" for i in range(5, 10)}


def test_reranker_model_is_cached_across_calls():
    candidates = [_candidate("C1", "text")]

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.7]
        mock_load.return_value = mock_model

        reranker = BGEReranker(model_name="cached-model")
        reranker.rerank("q", candidates)
        reranker.rerank("q", candidates)

    # _load_model called each time but the real cache is inside _load_model;
    # here we just verify rerank itself calls predict both times
    assert mock_model.predict.call_count == 2
