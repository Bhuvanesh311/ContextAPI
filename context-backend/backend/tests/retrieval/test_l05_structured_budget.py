"""
Tests for:
  - PostgresStructuredStoreAdapter  (exact-phrase + version-scope matching)
  - Budget guard in service execute_fn  (tokens / cost enforcement)
  - Reranker max_candidates from profile controls
  - SEMANTIC → HYBRID requirement mapping
  - L03 LLM token/cost tracking in QueryAnalysisResult

No database, no network, no model downloads.
Run from the backend folder:
    python -m pytest tests/retrieval/test_l05_structured_budget.py -v
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.core.enums import RetrievalRequirementType
from app.retrieval.engine.adapters.structured_store import (
    PostgresStructuredStoreAdapter,
    StructuredSearchRequest,
)
from app.retrieval.engine.reranker import BGEReranker
from app.retrieval.engine.schemas import (
    CandidateEvidence,
    CandidateEvidenceSet,
    ProvenanceMetadata,
)
from app.retrieval.engine.enums import ExecutionStatus, OperatorType


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _prov():
    return ProvenanceMetadata(
        document_id="DOC1", document_version_id="V1", chunk_id="C1",
        source_type="test", step_id="s1", operator_type=OperatorType.SEMANTIC,
    )


def _candidate(chunk_id="C1", content="hello", score=0.5):
    return CandidateEvidence(
        content=content, provenance=_prov(), score=score,
    )


class FakeRow:
    def __init__(self, chunk_id, content, document_version_id="V1"):
        self.chunk_id = chunk_id
        self.content = content
        self.document_version_id = document_version_id

    def __getitem__(self, item):
        return (self.chunk_id,)[item]


class FakeQuery:
    """Minimal SQLAlchemy query stub that records filter calls and returns rows."""

    def __init__(self, rows=None):
        self._rows = rows or []
        self._filters = []
        self._limit = None

    def filter(self, *args, **kwargs):
        self._filters.append(args)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def all(self):
        return [SimpleNamespace(__getitem__=lambda s, i: [r.chunk_id][i]) for r in self._rows]


class FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []
        self._last_query = None

    def query(self, *args):
        q = FakeQuery(self._rows)
        self._last_query = q
        return q


# ─────────────────────────────────────────────────────────────────────────────
# Structured adapter tests
# ─────────────────────────────────────────────────────────────────────────────

def _row(chunk_id):
    """Row that returns chunk_id from index 0 (matching how query.all() is used)."""
    r = MagicMock()
    r.__getitem__ = MagicMock(side_effect=lambda i: chunk_id if i == 0 else None)
    return r


def _adapter_with_rows(*chunk_ids):
    """Returns an adapter backed by a fake session that yields the given chunk_ids."""
    session = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.all.return_value = [_row(c) for c in chunk_ids]
    session.query.return_value = query_chain
    return PostgresStructuredStoreAdapter(session), session


def test_adapter_returns_lexical_prefixed_vector_ids():
    adapter, _ = _adapter_with_rows("chunk-001", "chunk-002")
    req = StructuredSearchRequest(
        query_text='Find the exact match for "error 404"',
        top_k=10,
        filters={"document_version_id": {"$in": ["V1", "V2"]}},
    )
    results = adapter.search(req, step_id="step-1")
    assert len(results) == 2
    assert all(r.vector_id.startswith("lexical_") for r in results)
    assert {r.vector_id for r in results} == {"lexical_chunk-001", "lexical_chunk-002"}


def test_adapter_score_is_always_one():
    adapter, _ = _adapter_with_rows("c1")
    req = StructuredSearchRequest(
        query_text='"exact phrase"',
        top_k=5,
        filters={"document_version_id": {"$in": ["V1"]}},
    )
    results = adapter.search(req, step_id="s1")
    assert results[0].score == 1.0


def test_adapter_metadata_hit_marks_match_type():
    adapter, _ = _adapter_with_rows("c1")
    req = StructuredSearchRequest(
        query_text='"phrase"',
        top_k=5,
        filters={"document_version_id": {"$in": ["V1"]}},
    )
    result = adapter.search(req, step_id="s1")[0]
    assert result.metadata_hits.get("match_type") == "exact_phrase"


def test_adapter_refuses_search_without_version_scope():
    from app.retrieval.engine.exceptions import ScopeViolationError

    session = MagicMock()
    adapter = PostgresStructuredStoreAdapter(session)
    req = StructuredSearchRequest(
        query_text='"exact phrase"',
        top_k=10,
        filters={},
    )
    with pytest.raises(ScopeViolationError):
        adapter.search(req, step_id="s1")
    session.query.assert_not_called()


def test_adapter_handles_tuple_version_ids():
    """_freeze_dict converts lists to tuples; the adapter must handle both."""
    adapter, session = _adapter_with_rows("c1")
    req = StructuredSearchRequest(
        query_text='"test"',
        top_k=5,
        filters={"document_version_id": {"$in": ("V1", "V2")}},
    )
    results = adapter.search(req, step_id="s1")
    assert len(results) == 1


def test_adapter_handles_direct_list_version_ids():
    adapter, _ = _adapter_with_rows("c1")
    req = StructuredSearchRequest(
        query_text='"query"',
        top_k=5,
        filters={"document_version_id": ["V1", "V2"]},
    )
    results = adapter.search(req, step_id="s1")
    assert len(results) == 1


def test_adapter_empty_when_no_phrase_but_scope_present():
    """Bug 1: 'exact' keyword with no quoted phrase must return [], not random chunks."""
    session = MagicMock()
    adapter = PostgresStructuredStoreAdapter(session)
    req = StructuredSearchRequest(
        query_text="what is the exact deadline",  # 'exact' word, no quotes
        top_k=10,
        filters={"document_version_id": {"$in": ["V1", "V2"]}},
    )
    results = adapter.search(req, step_id="s1")
    assert results == []
    session.query.assert_not_called()


def test_adapter_smart_quotes_treated_as_phrases():
    """Curly/smart quotes (“”) are recognised as phrase delimiters."""
    adapter, _ = _adapter_with_rows("c1")
    req = StructuredSearchRequest(
        query_text="“error 404”",  # "error 404"
        top_k=5,
        filters={"document_version_id": {"$in": ["V1"]}},
    )
    results = adapter.search(req, step_id="s1")
    assert len(results) == 1


def test_adapter_ilike_escapes_percent_in_phrase():
    """A phrase containing '%' must not turn into a wildcard."""
    session = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.all.return_value = []
    session.query.return_value = query_chain

    adapter = PostgresStructuredStoreAdapter(session)
    req = StructuredSearchRequest(
        query_text='"100% complete"',
        top_k=5,
        filters={"document_version_id": {"$in": ["V1"]}},
    )
    adapter.search(req, step_id="s1")

    # Verify the ilike call was made (filter applied)
    assert query_chain.filter.called
    # The first call (version_id filter) and second (ilike) should be present
    assert query_chain.filter.call_count >= 2


def test_adapter_multiple_phrases_all_applied():
    """Two quoted phrases → two ILIKE filter calls."""
    session = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.all.return_value = []
    session.query.return_value = query_chain

    adapter = PostgresStructuredStoreAdapter(session)
    req = StructuredSearchRequest(
        query_text='Find "error 404" and "timeout exceeded"',
        top_k=10,
        filters={"document_version_id": {"$in": ["V1"]}},
    )
    adapter.search(req, step_id="s1")
    # filter called once for version_ids + once per phrase (2 phrases) = 3
    assert query_chain.filter.call_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# Budget guard tests
# ─────────────────────────────────────────────────────────────────────────────

def _evidence_set(tokens=0, cost=0.0):
    return CandidateEvidenceSet(
        plan_id="PLAN1",
        status=ExecutionStatus.SUCCESS,
        tokens_used=tokens,
        cost_used=cost,
    )


def _make_execute_fn(executor_results, plan_limits, initial_tokens=0, initial_cost=0.0):
    """
    Reproduces the budget-guard closure from service.py for unit testing.
    executor_results: list of CandidateEvidenceSet to return on successive calls.
    """
    from app.retrieval.planning.schemas import ExecutionLimits

    class _StageError(Exception):
        def __init__(self, code, msg):
            super().__init__(msg)
            self.code = code

    lims = ExecutionLimits(**plan_limits)
    _budget = [initial_tokens, initial_cost]
    call_count = [0]

    def execute_fn(_plan, _top_k):
        if lims.max_tokens is not None and _budget[0] >= lims.max_tokens:
            raise _StageError("BUDGET_EXHAUSTED", f"Token budget: {_budget[0]}/{lims.max_tokens}")
        if lims.max_cost is not None and _budget[1] >= lims.max_cost:
            raise _StageError("BUDGET_EXHAUSTED", f"Cost budget: {_budget[1]}/{lims.max_cost}")
        result = executor_results[call_count[0] % len(executor_results)]
        call_count[0] += 1
        _budget[0] += result.tokens_used
        _budget[1] += result.cost_used
        return result

    return execute_fn, _StageError, _budget


def test_budget_guard_passes_when_under_token_limit():
    fn, err_cls, budget = _make_execute_fn(
        [_evidence_set(tokens=10)],
        {"max_tokens": 100},
    )
    result = fn(None, 5)
    assert result.tokens_used == 10
    assert budget[0] == 10


def test_budget_guard_blocks_when_token_limit_already_met():
    fn, err_cls, _ = _make_execute_fn(
        [_evidence_set(tokens=0)],
        {"max_tokens": 50},
        initial_tokens=50,
    )
    with pytest.raises(err_cls) as exc:
        fn(None, 5)
    assert exc.value.code == "BUDGET_EXHAUSTED"


def test_budget_guard_accumulates_across_rounds():
    fn, err_cls, budget = _make_execute_fn(
        [_evidence_set(tokens=40)],
        {"max_tokens": 100},
    )
    fn(None, 5)   # budget = 40  (40 < 100, ok)
    fn(None, 5)   # budget = 80  (80 < 100, ok)
    fn(None, 5)   # budget = 120 (80 < 100 at check → ok, then budget grows to 120)
    with pytest.raises(err_cls):
        fn(None, 5)  # 120 >= 100 → BUDGET_EXHAUSTED


def test_budget_guard_cost_enforcement():
    fn, err_cls, _ = _make_execute_fn(
        [_evidence_set(cost=0.03)],
        {"max_cost": 0.05},
        initial_cost=0.04,  # 0.04 < 0.05 → first call allowed; budget → 0.07
    )
    fn(None, 5)  # succeeds: 0.04 < 0.05; budget grows to 0.07
    with pytest.raises(err_cls) as exc:
        fn(None, 5)  # 0.07 >= 0.05 → BUDGET_EXHAUSTED
    assert exc.value.code == "BUDGET_EXHAUSTED"


def test_budget_guard_no_limit_never_blocks():
    fn, err_cls, budget = _make_execute_fn(
        [_evidence_set(tokens=9999, cost=9999.0)],
        {},  # max_tokens=None, max_cost=None
    )
    fn(None, 5)
    fn(None, 5)
    assert budget[0] == 9999 * 2


def test_l03_usage_pre_charges_budget():
    """Budget is initialized with L03 LLM usage, not zero."""
    fn, err_cls, budget = _make_execute_fn(
        [_evidence_set(tokens=0)],
        {"max_tokens": 200},
        initial_tokens=150,   # L03 used 150 tokens
    )
    fn(None, 5)               # round 1 — budget still < 200, ok
    # After round 1 budget = 150; still under 200
    assert budget[0] == 150


# ─────────────────────────────────────────────────────────────────────────────
# Reranker max_candidates from profile
# ─────────────────────────────────────────────────────────────────────────────

def test_reranker_respects_profile_max_candidates():
    candidates = [
        CandidateEvidence(
            content=f"text {i}",
            provenance=_prov(),
            score=float(i),
        )
        for i in range(30)
    ]
    scored = list(range(20))

    with patch("app.retrieval.engine.reranker._load_model") as mock_load:
        mock_model = MagicMock()
        mock_model.predict.return_value = scored
        mock_load.return_value = mock_model

        # FAST profile uses max_candidates=20
        reranker = BGEReranker(model_name="test", max_candidates=20)
        result = reranker.rerank("query", candidates)

    call_pairs = mock_model.predict.call_args[0][0]
    assert len(call_pairs) == 20
    assert len(result) == 30  # all 30 returned


# ─────────────────────────────────────────────────────────────────────────────
# SEMANTIC → HYBRID requirement mapping
# ─────────────────────────────────────────────────────────────────────────────

def test_semantic_maps_to_hybrid_after_adjustment():
    """Mirrors the _REQUIREMENT_MAP logic in service.py."""
    reqs = [RetrievalRequirementType.SEMANTIC]
    _REQUIREMENT_MAP = {
        RetrievalRequirementType.SEMANTIC: RetrievalRequirementType.HYBRID,
        RetrievalRequirementType.RELATIONAL: RetrievalRequirementType.HYBRID,
    }
    adjusted = list(dict.fromkeys(_REQUIREMENT_MAP.get(r, r) for r in reqs))
    assert adjusted == [RetrievalRequirementType.HYBRID]


def test_relational_maps_to_hybrid():
    reqs = [RetrievalRequirementType.RELATIONAL]
    _REQUIREMENT_MAP = {
        RetrievalRequirementType.SEMANTIC: RetrievalRequirementType.HYBRID,
        RetrievalRequirementType.RELATIONAL: RetrievalRequirementType.HYBRID,
    }
    adjusted = list(dict.fromkeys(_REQUIREMENT_MAP.get(r, r) for r in reqs))
    assert adjusted == [RetrievalRequirementType.HYBRID]


def test_exact_passes_through_unchanged():
    reqs = [RetrievalRequirementType.EXACT]
    _REQUIREMENT_MAP = {
        RetrievalRequirementType.SEMANTIC: RetrievalRequirementType.HYBRID,
        RetrievalRequirementType.RELATIONAL: RetrievalRequirementType.HYBRID,
    }
    adjusted = list(dict.fromkeys(_REQUIREMENT_MAP.get(r, r) for r in reqs))
    assert adjusted == [RetrievalRequirementType.EXACT]


def test_hybrid_not_duplicated_when_semantic_and_hybrid_both_present():
    reqs = [RetrievalRequirementType.SEMANTIC, RetrievalRequirementType.HYBRID]
    _REQUIREMENT_MAP = {
        RetrievalRequirementType.SEMANTIC: RetrievalRequirementType.HYBRID,
        RetrievalRequirementType.RELATIONAL: RetrievalRequirementType.HYBRID,
    }
    adjusted = list(dict.fromkeys(_REQUIREMENT_MAP.get(r, r) for r in reqs))
    assert adjusted == [RetrievalRequirementType.HYBRID]  # deduped


# ─────────────────────────────────────────────────────────────────────────────
# L03 token/cost tracking
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_skipped_when_token_budget_too_tight():
    """Bug 2: tight budget → Tier B/C skipped so retrieval can still run."""
    from app.retrieval.intelligence.aggregate import analyze_request
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.security.profiles import controls_for

    contract = RetrievalContract(
        request_id="R_TIGHT",
        query="asdfghjkl zxcvbnm",  # UNKNOWN intent → would normally trigger LLM
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.DEEP,
        lifecycle=LifecycleContext(request_id="R_TIGHT"),
    )
    deep_controls = controls_for(ExecutionProfile.DEEP)
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        profile=ExecutionProfile.DEEP,
        controls=deep_controls,
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    with patch("app.retrieval.intelligence.aggregate._get_router") as mock_router_fn:
        mock_router = MagicMock()
        mock_router_fn.return_value = mock_router

        # max_tokens=1 is far below any LLM estimate → LLM must be skipped
        result = analyze_request(scoped, max_tokens=1)

    # LLM was skipped: no tokens used, router never called
    assert result.llm_tokens_used == 0
    assert result.llm_cost_used == 0.0
    mock_router.execute_tier_b.assert_not_called()
    mock_router.execute_tier_c.assert_not_called()


def test_llm_skipped_when_cost_budget_too_tight():
    """Bug 2 (cost variant): near-zero cost budget → LLM skipped."""
    from app.retrieval.intelligence.aggregate import analyze_request
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.security.profiles import controls_for

    contract = RetrievalContract(
        request_id="R_CHEAP",
        query="asdfghjkl",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.COLLABORATIVE,
        lifecycle=LifecycleContext(request_id="R_CHEAP"),
    )
    collab_controls = controls_for(ExecutionProfile.COLLABORATIVE)
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        profile=ExecutionProfile.COLLABORATIVE,
        controls=collab_controls,
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    with patch("app.retrieval.intelligence.aggregate._get_router") as mock_router_fn:
        mock_router = MagicMock()
        mock_router_fn.return_value = mock_router

        result = analyze_request(scoped, max_cost=0.0)  # $0 budget

    assert result.llm_tokens_used == 0
    mock_router.execute_tier_b.assert_not_called()


def test_tier_a_only_returns_zero_usage():
    from app.retrieval.intelligence.schemas import QueryAnalysisResult, QueryIntelligence
    from app.core.enums import QueryIntent, QueryComplexity, AnalysisMethod, MemoryRequirement
    from app.retrieval.intelligence.schemas import (
        ObjectIntelligence, QuerySafetyAssessment, DecompositionResult,
    )
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.security.profiles import controls_for

    contract = RetrievalContract(
        request_id="R1",
        query="What is the rate limit?",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.STANDARD,
        lifecycle=LifecycleContext(request_id="R1"),
    )
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    from app.retrieval.intelligence.aggregate import analyze_request
    result = analyze_request(scoped)

    assert result.llm_tokens_used == 0
    assert result.llm_cost_used == 0.0


@patch("app.retrieval.intelligence.aggregate.settings.QUERY_ANALYSIS_LLM_ENABLED", True)
def test_tier_b_populates_token_count():
    from app.retrieval.intelligence.aggregate import analyze_request
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.security.profiles import controls_for

    # UNKNOWN ambiguous query so needs_llm = True in aggregate.py
    contract = RetrievalContract(
        request_id="R2",
        query="asdfghjkl zxcvbnm",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.DEEP,
        lifecycle=LifecycleContext(request_id="R2"),
    )
    deep_controls = controls_for(ExecutionProfile.DEEP)  # allow_llm=True
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        profile=ExecutionProfile.DEEP,
        controls=deep_controls,
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    fake_llm_response = {"intent": "FACT_LOOKUP", "complexity": "LOW", "ambiguity_score": 0.1, "requires_relational": False}

    with patch("app.retrieval.intelligence.aggregate._get_router") as mock_router_fn:
        mock_router = MagicMock()
        mock_router.execute_tier_b.return_value = fake_llm_response
        mock_router_fn.return_value = mock_router

        result = analyze_request(scoped)

    assert result.llm_tokens_used > 0
    assert result.llm_cost_used == 0.0  # Tier B (Ollama) is local — no monetary cost


@patch("app.retrieval.intelligence.aggregate.settings.QUERY_ANALYSIS_LLM_ENABLED", True)
def test_tier_c_populates_token_and_cost():
    from app.retrieval.intelligence.aggregate import analyze_request, _TIER_C_COST_PER_TOKEN
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.security.profiles import controls_for

    contract = RetrievalContract(
        request_id="R3",
        query="asdfghjkl",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.COLLABORATIVE,
        lifecycle=LifecycleContext(request_id="R3"),
    )
    collab_controls = controls_for(ExecutionProfile.COLLABORATIVE)  # allow_llm=True, max_llm_calls=2
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        profile=ExecutionProfile.COLLABORATIVE,
        controls=collab_controls,
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    fake_response = {"intent": "FACT_LOOKUP", "complexity": "LOW", "ambiguity_score": 0.1, "requires_relational": False}

    with patch("app.retrieval.intelligence.aggregate._get_router") as mock_router_fn:
        mock_router = MagicMock()
        mock_router.execute_tier_b.side_effect = RuntimeError("Ollama down")
        mock_router.execute_tier_c.return_value = fake_response
        mock_router_fn.return_value = mock_router

        result = analyze_request(scoped)

    assert result.llm_tokens_used > 0
    assert result.llm_cost_used > 0.0
    expected_cost = result.llm_tokens_used * _TIER_C_COST_PER_TOKEN
    assert result.llm_cost_used == pytest.approx(expected_cost)


def test_query_analysis_llm_disabled_skips_tier_b():
    """With QUERY_ANALYSIS_LLM_ENABLED off (the default), L03 never calls the model."""
    from app.retrieval.intelligence.aggregate import analyze_request
    from app.core.enums import RequestSourceType, ExecutionProfile
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.schemas import ActorModel, LifecycleContext
    from app.retrieval.security.schemas import ScopedRetrievalContract, ScopedDocument
    from app.retrieval.security.enums import AuthorizationDecision
    from app.retrieval.security.profiles import controls_for

    contract = RetrievalContract(
        request_id="R3",
        query="asdfghjkl zxcvbnm",
        source_type=RequestSourceType.USER,
        actor=ActorModel(actor_type="USER", actor_id="U1"),
        scope={"project_id": "P1"},
        profile=ExecutionProfile.DEEP,
        lifecycle=LifecycleContext(request_id="R3"),
    )
    scoped = ScopedRetrievalContract(
        request=contract,
        effective_scope={"document_version_id": {"$in": ["V1"]}},
        decision=AuthorizationDecision.ALLOW,
        profile=ExecutionProfile.DEEP,
        controls=controls_for(ExecutionProfile.DEEP),
        documents=[ScopedDocument(document_id="D1", name="a.pdf", document_version_id="V1")],
    )

    with patch("app.retrieval.intelligence.aggregate.settings.QUERY_ANALYSIS_LLM_ENABLED", False),          patch("app.retrieval.intelligence.aggregate._get_router") as mock_router_fn:
        result = analyze_request(scoped)

    mock_router_fn.return_value.execute_tier_b.assert_not_called()
    assert result.llm_tokens_used == 0
