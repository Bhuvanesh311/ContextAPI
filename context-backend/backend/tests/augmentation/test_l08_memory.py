"""
L8 Memory tests.

Covers: MemoryStore Redis operations, relevance scoring, load_memory(),
write_turn(), and memory context appearing in the prompt.

All tests mock the Redis client — no live Redis required.
"""

import json
import pytest
from unittest.mock import MagicMock, call, patch

from app.core.enums import RequestSourceType, ExecutionProfile
from app.augmentation.memory.schemas import MemorySourceType, RelevantMemoryPackage
from app.augmentation.memory.store import MemoryStore, SESSION_TTL, LONG_TERM_TTL, AGENT_TTL
from app.augmentation.memory.relevance import score_relevance
from app.augmentation.memory.service import load_memory, write_turn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redis() -> MagicMock:
    r = MagicMock()
    r.lrange.return_value = []
    r.keys.return_value = []
    r.get.return_value = None
    # Pipelined writes and SCAN go through the same mock methods, so tests can
    # assert on r.lpush / r.expire / r.keys directly.
    r.pipeline.return_value = r
    r.scan_iter.side_effect = lambda match, count=None: iter(r.keys(match))
    return r


def _store(redis=None) -> MemoryStore:
    return MemoryStore(redis or _redis())


# ---------------------------------------------------------------------------
# MemoryStore — session turns
# ---------------------------------------------------------------------------

def test_append_turn_calls_lpush_with_correct_key():
    r = _redis()
    store = _store(r)
    store.append_turn("COR001", {"query": "hello", "answer_summary": ""})
    r.lpush.assert_called_once()
    key, payload = r.lpush.call_args[0]
    assert key == "memory:session:COR001"
    parsed = json.loads(payload)
    assert parsed["query"] == "hello"


def test_append_turn_sets_ttl():
    r = _redis()
    store = _store(r)
    store.append_turn("COR001", {"query": "q"})
    r.expire.assert_called_once_with("memory:session:COR001", SESSION_TTL)


def test_append_turn_trims_list():
    r = _redis()
    store = _store(r)
    store.append_turn("COR001", {"query": "q"})
    r.ltrim.assert_called_once()


def test_load_turns_returns_parsed_dicts():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "first", "answer_summary": "ans1"}),
        json.dumps({"query": "second", "answer_summary": "ans2"}),
    ]
    store = _store(r)
    turns = store.load_turns("COR001", limit=5)
    assert len(turns) == 2
    assert turns[0]["query"] == "first"


def test_load_turns_skips_malformed_json():
    r = _redis()
    r.lrange.return_value = ["{bad json}", json.dumps({"query": "ok"})]
    store = _store(r)
    turns = store.load_turns("COR001")
    assert len(turns) == 1
    assert turns[0]["query"] == "ok"


def test_load_turns_empty_list():
    r = _redis()
    r.lrange.return_value = []
    turns = _store(r).load_turns("COR001")
    assert turns == []


# ---------------------------------------------------------------------------
# MemoryStore — long-term facts
# ---------------------------------------------------------------------------

def test_write_fact_uses_correct_key_pattern():
    r = _redis()
    _store(r).write_fact("USR1", "rate_limit", "limit is 100", {})
    key = r.set.call_args[0][0]
    assert key == "memory:lt:USR1:rate_limit"


def test_write_fact_sets_long_term_ttl():
    r = _redis()
    _store(r).write_fact("USR1", "fact1", "content", {})
    assert r.set.call_args[1]["ex"] == LONG_TERM_TTL


def test_load_facts_uses_wildcard_pattern():
    r = _redis()
    r.keys.return_value = []
    _store(r).load_facts("USR1")
    r.keys.assert_called_once_with("memory:lt:USR1:*")


def test_load_facts_returns_parsed_items():
    r = _redis()
    r.keys.return_value = ["memory:lt:USR1:fact1"]
    r.get.return_value = json.dumps({"content": "The auth uses JWT.", "metadata": {}})
    facts = _store(r).load_facts("USR1")
    assert len(facts) == 1
    assert facts[0]["content"] == "The auth uses JWT."


# ---------------------------------------------------------------------------
# MemoryStore — agent memory
# ---------------------------------------------------------------------------

def test_write_agent_uses_correct_key_pattern():
    r = _redis()
    _store(r).write_agent("AGT1", "task_state", "working on X", {})
    key = r.set.call_args[0][0]
    assert key == "memory:agent:AGT1:task_state"


def test_write_agent_sets_agent_ttl():
    r = _redis()
    _store(r).write_agent("AGT1", "k", "v", {})
    assert r.set.call_args[1]["ex"] == AGENT_TTL


def test_load_agent_returns_parsed_items():
    r = _redis()
    r.keys.return_value = ["memory:agent:AGT1:k1"]
    r.get.return_value = json.dumps({"content": "agent context", "metadata": {}})
    items = _store(r).load_agent("AGT1")
    assert items[0]["content"] == "agent context"


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def test_relevance_score_high_for_matching_content():
    score = score_relevance("What is the rate limit?", "The rate limit is 100 requests per second.")
    assert score > 0.3


def test_relevance_score_low_for_unrelated_content():
    score = score_relevance("What is the rate limit?", "The sky is blue on a sunny day.")
    assert score < 0.2


def test_relevance_score_zero_for_empty_query():
    assert score_relevance("", "some content") == 0.0


def test_relevance_score_zero_for_empty_content():
    assert score_relevance("What is the rate limit?", "") == 0.0


def test_relevance_score_bounded_0_to_1():
    score = score_relevance("rate limit authentication token", "rate limit authentication token")
    assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# load_memory()
# ---------------------------------------------------------------------------

def test_load_memory_returns_package():
    store = _store()
    pkg = load_memory("What is the rate limit?", store=store)
    assert isinstance(pkg, RelevantMemoryPackage)


def test_load_memory_session_items_populated():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "What is the rate limit?", "answer_summary": "100 req/s", "request_id": "R1", "ts": ""}),
    ]
    store = _store(r)
    pkg = load_memory("rate limit", correlation_id="COR1", store=store)
    assert len(pkg.session_items) == 1
    assert pkg.session_items[0].source_type == MemorySourceType.SESSION


def test_load_memory_no_session_when_no_correlation_id():
    r = _redis()
    store = _store(r)
    pkg = load_memory("query", correlation_id=None, store=store)
    assert pkg.session_items == []
    r.lrange.assert_not_called()


def test_load_memory_agent_items_only_for_agent_source_types():
    r = _redis()
    r.keys.side_effect = lambda pattern: (
        ["memory:agent:AGT1:k"] if "agent" in pattern else []
    )
    r.get.return_value = json.dumps({"content": "agent state", "metadata": {}})
    store = _store(r)

    # USER source_type → no agent items
    pkg_user = load_memory("q", actor_id="AGT1", source_type=RequestSourceType.USER, store=store)
    assert pkg_user.agent_items == []

    # AGENT source_type → agent items populated
    pkg_agent = load_memory("q", actor_id="AGT1", source_type=RequestSourceType.AGENT, store=store)
    assert len(pkg_agent.agent_items) == 1


def test_load_memory_long_term_filtered_by_relevance():
    r = _redis()
    r.keys.return_value = ["memory:lt:USR1:f1"]
    r.get.return_value = json.dumps({"content": "The sky is blue.", "metadata": {}})
    store = _store(r)
    # "rate limit" query — "The sky is blue." should score 0 → excluded
    pkg = load_memory("rate limit", user_id="USR1", store=store)
    assert pkg.long_term_items == []


def test_load_memory_total_items_count():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "rate limit", "answer_summary": "100/s", "request_id": "R1", "ts": ""}),
    ]
    store = _store(r)
    pkg = load_memory("rate limit", correlation_id="COR1", store=store)
    expected = (len(pkg.session_items) + len(pkg.long_term_items)
                + len(pkg.agent_items) + len(pkg.evidence_items))
    assert pkg.total_items == expected


def test_load_memory_all_items_sorted_by_relevance():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "rate limit", "answer_summary": "100/s", "request_id": "R1", "ts": ""}),
        json.dumps({"query": "auth token", "answer_summary": "JWT", "request_id": "R2", "ts": ""}),
    ]
    store = _store(r)
    pkg = load_memory("rate limit", correlation_id="COR1", store=store)
    items = pkg.all_items()
    scores = [i.relevance_score for i in items]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# write_turn()
# ---------------------------------------------------------------------------

def test_write_turn_appends_to_session():
    r = _redis()
    store = _store(r)
    write_turn("COR1", "What is X?", "REQ1", answer_summary="X is Y.", store=store)
    r.lpush.assert_called_once()
    key, payload = r.lpush.call_args[0]
    assert key == "memory:session:COR1"
    data = json.loads(payload)
    assert data["query"] == "What is X?"
    assert data["answer_summary"] == "X is Y."
    assert data["request_id"] == "REQ1"


def test_write_turn_noop_without_correlation_id():
    r = _redis()
    store = _store(r)
    write_turn("", "query", "REQ1", store=store)
    r.lpush.assert_not_called()


def test_write_turn_truncates_long_answer():
    r = _redis()
    store = _store(r)
    long_answer = "x" * 500
    write_turn("COR1", "q", "R1", answer_summary=long_answer, store=store)
    _, payload = r.lpush.call_args[0]
    data = json.loads(payload)
    assert len(data["answer_summary"]) <= 200


# ---------------------------------------------------------------------------
# Memory appears in prompt
# ---------------------------------------------------------------------------

def test_memory_items_appear_in_built_prompt():
    from app.augmentation.memory.schemas import MemoryItem, RelevantMemoryPackage, MemorySourceType
    from app.augmentation.prompt_builder import build_prompt
    from app.augmentation.schemas import AssembledContext, ContextItem
    from app.core.enums import QueryIntent

    mem_item = MemoryItem(
        item_id="sess_0", source_type=MemorySourceType.SESSION,
        content="Q: What is the rate limit? A: 100 req/s",
        relevance_score=0.8,
    )
    pkg = RelevantMemoryPackage(session_items=[mem_item], total_items=1, total_tokens=10)

    ctx_item = ContextItem(rank=1, evidence_id="ev1", content="docs say 100/s",
                           document_id="D1", chunk_id="c1", score=0.9, tokens=5)
    ctx = AssembledContext(items=[ctx_item], total_tokens=5, budget_tokens=3000)

    prompt = build_prompt("rate limit?", QueryIntent.FACT_LOOKUP, ctx, memory_package=pkg)
    assert "Conversation Memory" in prompt.user_prompt
    assert "[M1]" in prompt.user_prompt
    assert "rate limit" in prompt.user_prompt


def test_no_memory_section_when_package_empty():
    from app.augmentation.memory.schemas import RelevantMemoryPackage
    from app.augmentation.prompt_builder import build_prompt
    from app.augmentation.schemas import AssembledContext, ContextItem
    from app.core.enums import QueryIntent

    pkg = RelevantMemoryPackage()
    ctx_item = ContextItem(rank=1, evidence_id="ev1", content="content",
                           document_id="D1", chunk_id="c1", score=0.9, tokens=2)
    ctx = AssembledContext(items=[ctx_item], total_tokens=2, budget_tokens=3000)

    prompt = build_prompt("Q?", QueryIntent.FACT_LOOKUP, ctx, memory_package=pkg)
    assert "Conversation Memory" not in prompt.user_prompt


# ---------------------------------------------------------------------------
# Gap 1: Shared Evidence — append_evidence_chunks / load_evidence_chunks
# ---------------------------------------------------------------------------

def test_evidence_chunks_stored_in_redis():
    r = _redis()
    store = _store(r)
    chunks = [
        {"chunk_id": "c1", "document_id": "D1", "document_name": "doc.pdf",
         "content_snippet": "rate limit is 100", "score": 0.9, "request_id": "R1",
         "ts": "2026-10-06T10:00:00+00:00", "scope": {}},
    ]
    store.append_evidence_chunks("COR1", chunks)

    key, payload = r.lpush.call_args[0]
    assert key == "memory:evidence:COR1"
    parsed = json.loads(payload)
    assert parsed["chunk_id"] == "c1"
    r.ltrim.assert_called_once()
    r.expire.assert_called_once_with("memory:evidence:COR1", SESSION_TTL)


def test_evidence_chunks_loaded_as_memory_items():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"chunk_id": "c1", "document_id": "D1", "document_name": "doc.pdf",
                    "content_snippet": "rate limit is 100", "score": 0.9, "request_id": "R1",
                    "ts": "2026-10-06T10:00:00+00:00", "scope": {}}),
    ]
    store = _store(r)
    chunks = store.load_evidence_chunks("COR1", limit=5)
    assert len(chunks) == 1
    assert chunks[0]["chunk_id"] == "c1"
    assert chunks[0]["document_name"] == "doc.pdf"


def test_load_memory_includes_evidence_items():
    from app.augmentation.memory.service import write_evidence_chunks

    r = _redis()

    # First call (lrange) is for session turns; second is for evidence.
    # Use side_effect to distinguish them by key prefix.
    evidence_payload = json.dumps({
        "chunk_id": "c1", "document_id": "D1", "document_name": "api_docs.pdf",
        "content_snippet": "The rate limit is 100 req/s",
        "score": 0.9, "request_id": "R1",
        "ts": "2026-10-06T10:00:00+00:00", "scope": {},
    })

    def lrange_side(key, start, end):
        if "evidence" in key:
            return [evidence_payload]
        return []

    r.lrange.side_effect = lrange_side
    store = _store(r)

    pkg = load_memory("rate limit", correlation_id="COR1", store=store)
    assert len(pkg.evidence_items) == 1
    assert pkg.evidence_items[0].source_type == MemorySourceType.EVIDENCE
    assert "api_docs.pdf" in pkg.evidence_items[0].content


def test_write_evidence_chunks_stores_top_n():
    from app.augmentation.memory.service import write_evidence_chunks

    r = _redis()
    store = _store(r)

    # Build mock evidence items with .source and .content attributes
    def _ev(chunk_id, doc_id, name, content, score):
        item = MagicMock()
        item.source.chunk_id = chunk_id
        item.source.document_id = doc_id
        item.source.document_name = name
        item.content = content
        item.score = score
        return item

    evidence = [_ev(f"c{i}", f"D{i}", f"doc{i}.pdf", f"content {i}", 0.9 - i * 0.05) for i in range(15)]
    write_evidence_chunks("COR1", "R1", evidence, store=store)

    # lpush called once per chunk, max 10 stored
    assert r.lpush.call_count == 10


# ---------------------------------------------------------------------------
# Gap 2: Scope enforcement — project isolation
# ---------------------------------------------------------------------------

def test_scope_filters_session_turns():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "q1", "answer_summary": "a1", "request_id": "R1",
                    "ts": "", "scope": {"project_id": "PROJ_A"}}),
        json.dumps({"query": "q2", "answer_summary": "a2", "request_id": "R2",
                    "ts": "", "scope": {"project_id": "PROJ_B"}}),
    ]
    store = _store(r)
    turns = store.load_turns("COR1", scope={"project_id": "PROJ_A"})
    assert len(turns) == 1
    assert turns[0]["query"] == "q1"


def test_scope_noop_when_no_scope_given():
    r = _redis()
    r.lrange.return_value = [
        json.dumps({"query": "q1", "answer_summary": "", "request_id": "R1",
                    "ts": "", "scope": {"project_id": "PROJ_A"}}),
        json.dumps({"query": "q2", "answer_summary": "", "request_id": "R2",
                    "ts": "", "scope": {"project_id": "PROJ_B"}}),
    ]
    store = _store(r)
    turns = store.load_turns("COR1", scope=None)
    assert len(turns) == 2


def test_scope_filters_facts_by_project_id():
    r = _redis()
    r.keys.return_value = ["memory:lt:USR1:f1", "memory:lt:USR1:f2"]

    def get_side(key):
        if key.endswith("f1"):
            return json.dumps({"content": "fact A", "metadata": {"scope": {"project_id": "PROJ_A"}}})
        return json.dumps({"content": "fact B", "metadata": {"scope": {"project_id": "PROJ_B"}}})

    r.get.side_effect = get_side
    store = _store(r)
    facts = store.load_facts("USR1", scope={"project_id": "PROJ_A"})
    assert len(facts) == 1
    assert facts[0]["content"] == "fact A"


def test_scope_filters_agent_by_project_id():
    r = _redis()
    r.keys.return_value = ["memory:agent:AGT1:k1"]
    r.get.return_value = json.dumps({
        "content": "agent state",
        "metadata": {"scope": {"project_id": "PROJ_X"}},
    })
    store = _store(r)
    # Query for a different project — should return nothing
    items = store.load_agent("AGT1", scope={"project_id": "PROJ_Y"})
    assert items == []


def test_write_turn_stores_scope_in_payload():
    r = _redis()
    store = _store(r)
    write_turn("COR1", "What is X?", "R1", answer_summary="X is Y.",
               scope={"project_id": "PROJ_A"}, store=store)
    _, payload = r.lpush.call_args[0]
    data = json.loads(payload)
    assert data["scope"] == {"project_id": "PROJ_A"}


def test_write_turn_stores_empty_scope_when_none():
    r = _redis()
    store = _store(r)
    write_turn("COR1", "q", "R1", scope=None, store=store)
    _, payload = r.lpush.call_args[0]
    data = json.loads(payload)
    assert data["scope"] == {}


# ---------------------------------------------------------------------------
# Gap 3: Priority scoring — three-dimensional ranking
# ---------------------------------------------------------------------------

def test_priority_score_agent_higher_than_session():
    from app.augmentation.memory.relevance import compute_priority_score

    agent_score   = compute_priority_score(0.5, MemorySourceType.AGENT,   "")
    session_score = compute_priority_score(0.5, MemorySourceType.SESSION, "")
    assert agent_score > session_score


def test_priority_score_evidence_higher_than_long_term():
    from app.augmentation.memory.relevance import compute_priority_score

    evidence_score   = compute_priority_score(0.5, MemorySourceType.EVIDENCE,  "")
    long_term_score  = compute_priority_score(0.5, MemorySourceType.LONG_TERM, "")
    assert evidence_score > long_term_score


def test_priority_score_recent_higher_than_old():
    from app.augmentation.memory.relevance import compute_priority_score
    from datetime import datetime, timezone, timedelta

    recent = datetime.now(timezone.utc).isoformat()
    old    = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()

    recent_score = compute_priority_score(0.5, MemorySourceType.SESSION, recent)
    old_score    = compute_priority_score(0.5, MemorySourceType.SESSION, old)
    assert recent_score > old_score


def test_priority_score_formula_bounds():
    from app.augmentation.memory.relevance import compute_priority_score

    # At extremes: max is AGENT + relevance=1.0 + recency=1.0
    max_score = compute_priority_score(1.0, MemorySourceType.AGENT, "")  # recency=0.5 (no ts)
    assert 0.0 <= max_score <= 1.0

    min_score = compute_priority_score(0.0, MemorySourceType.SESSION, "")
    assert 0.0 <= min_score <= 1.0


def test_all_items_sorted_by_priority_score():
    from app.augmentation.memory.schemas import MemoryItem, RelevantMemoryPackage

    item_agent = MemoryItem(
        item_id="a1", source_type=MemorySourceType.AGENT,
        content="agent state", relevance_score=0.4, priority_score=0.7,
    )
    item_session = MemoryItem(
        item_id="s1", source_type=MemorySourceType.SESSION,
        content="session turn", relevance_score=0.9, priority_score=0.3,
    )
    # agent has lower relevance but higher priority_score
    pkg = RelevantMemoryPackage(
        session_items=[item_session],
        agent_items=[item_agent],
        total_items=2,
        total_tokens=10,
    )
    items = pkg.all_items()
    assert items[0].item_id == "a1"   # priority_score 0.7 first
    assert items[1].item_id == "s1"   # priority_score 0.3 second


def test_total_items_includes_evidence():
    r = _redis()

    def lrange_side(key, start, end):
        if "evidence" in key:
            return [json.dumps({
                "chunk_id": "c1", "document_id": "D1", "document_name": "doc.pdf",
                "content_snippet": "rate limit 100", "score": 0.9,
                "request_id": "R1", "ts": "", "scope": {},
            })]
        if "session" in key:
            return [json.dumps({"query": "rate limit", "answer_summary": "100/s",
                                "request_id": "R1", "ts": "", "scope": {}})]
        return []

    r.lrange.side_effect = lrange_side
    store = _store(r)
    pkg = load_memory("rate limit", correlation_id="COR1", store=store)
    assert pkg.total_items == len(pkg.session_items) + len(pkg.long_term_items) + len(pkg.agent_items) + len(pkg.evidence_items)
