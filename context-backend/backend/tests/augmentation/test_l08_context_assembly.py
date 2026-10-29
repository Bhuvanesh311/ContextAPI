"""
L8 Context Assembly tests.

Verifies that assemble_context() correctly sorts evidence by score, respects the
token budget, trims oversized chunks, and handles edge cases.
"""

import pytest
from unittest.mock import MagicMock

from app.augmentation.context_assembly import assemble_context, _DEFAULT_BUDGET_TOKENS, _MAX_ITEM_TOKENS
from app.augmentation.schemas import AssembledContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_package(items: list[tuple[str, str, float]]):
    """
    items: list of (evidence_id, content, score)
    Returns a mock EvidencePackage with .evidence populated.
    """
    package = MagicMock()
    package.evidence = []
    for eid, content, score in items:
        item = MagicMock()
        item.evidence_id = eid
        item.content = content
        item.score = score
        item.source.document_id = "DOC1"
        item.source.document_name = "doc.pdf"
        item.source.chunk_id = f"chunk_{eid}"
        package.evidence.append(item)
    return package


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_package_returns_empty_context():
    package = _make_package([])
    ctx = assemble_context(package)
    assert ctx.items == []
    assert ctx.total_tokens == 0
    assert not ctx.truncated


def test_l07_order_is_kept_not_raw_score():
    # Scores mix RRF and cross-encoder logits, so L07's order is authoritative.
    package = _make_package([
        ("e1", "first ranked chunk by L07", 0.01),
        ("e2", "second ranked chunk by L07", 5.2),
        ("e3", "third ranked chunk by L07", -1.0),
    ])
    ctx = assemble_context(package)
    assert [i.evidence_id for i in ctx.items] == ["e1", "e2", "e3"]
    assert [i.rank for i in ctx.items] == [1, 2, 3]


def test_budget_respected():
    # Each chunk ~100 tokens; budget 250 fits 2 whole items, the 3rd is
    # compressed into the 50 tokens left only if >= _MIN_COMPRESSED_TOKENS.
    package = _make_package([
        ("e1", "a" * 400, 0.9),
        ("e2", "b" * 400, 0.8),
        ("e3", "c" * 400, 0.7),
    ])
    ctx = assemble_context(package, budget_tokens=250)
    assert len(ctx.items) == 2
    assert ctx.truncated is True
    assert ctx.total_tokens <= 250


def test_long_chunk_trimmed():
    long_content = "a" * (_MAX_ITEM_TOKENS * 8)  # 8x the limit
    package = _make_package([("e1", long_content, 1.0)])
    ctx = assemble_context(package)
    assert len(ctx.items) == 1
    assert ctx.items[0].tokens <= _MAX_ITEM_TOKENS
    assert ctx.truncated is True


def test_rank_assignment_is_sequential():
    package = _make_package([
        ("e1", "content a", 0.9),
        ("e2", "content b", 0.7),
        ("e3", "content c", 0.5),
    ])
    ctx = assemble_context(package)
    ranks = [item.rank for item in ctx.items]
    assert ranks == list(range(1, len(ctx.items) + 1))


def test_context_item_fields_populated():
    package = _make_package([("ev1", "hello world", 0.8)])
    ctx = assemble_context(package)
    item = ctx.items[0]
    assert item.evidence_id == "ev1"
    assert item.content == "hello world"
    assert item.document_id == "DOC1"
    assert item.chunk_id == "chunk_ev1"
    assert item.score == 0.8


def test_single_item_within_budget_not_truncated():
    package = _make_package([("e1", "short", 1.0)])
    ctx = assemble_context(package, budget_tokens=_DEFAULT_BUDGET_TOKENS)
    assert len(ctx.items) == 1
    assert not ctx.truncated


def test_custom_budget_zero_returns_empty():
    package = _make_package([("e1", "content", 0.5)])
    ctx = assemble_context(package, budget_tokens=0)
    assert ctx.items == []
    assert ctx.truncated is True


def test_total_tokens_matches_sum_of_item_tokens():
    package = _make_package([
        ("e1", "abc def ghi", 0.9),
        ("e2", "xyz mno pqr", 0.8),
    ])
    ctx = assemble_context(package)
    assert ctx.total_tokens == sum(item.tokens for item in ctx.items)


def test_budget_tokens_field_reflects_input():
    package = _make_package([("e1", "text", 0.5)])
    ctx = assemble_context(package, budget_tokens=1234)
    assert ctx.budget_tokens == 1234


# ---------------------------------------------------------------------------
# Chunk deduplication
# ---------------------------------------------------------------------------

def _make_package_with_chunk_ids(items: list[tuple[str, str, float, str]]):
    """items: (evidence_id, content, score, chunk_id)"""
    package = MagicMock()
    package.evidence = []
    for eid, content, score, chunk_id in items:
        item = MagicMock()
        item.evidence_id = eid
        item.content = content
        item.score = score
        item.source.document_id = "DOC1"
        item.source.document_name = "doc.pdf"
        item.source.chunk_id = chunk_id
        package.evidence.append(item)
    return package


def test_duplicate_chunk_id_included_only_once():
    package = _make_package_with_chunk_ids([
        ("e1", "content from path A", 0.9, "chunk_001"),
        ("e2", "content from path B", 0.85, "chunk_001"),  # same chunk, lower score
        ("e3", "different chunk", 0.7, "chunk_002"),
    ])
    ctx = assemble_context(package)
    chunk_ids = [item.chunk_id for item in ctx.items]
    assert chunk_ids.count("chunk_001") == 1
    assert len(ctx.items) == 2


def test_dedup_keeps_highest_score_occurrence():
    package = _make_package_with_chunk_ids([
        ("e1", "high score version", 0.9, "chunk_X"),
        ("e2", "low score version",  0.4, "chunk_X"),
    ])
    ctx = assemble_context(package)
    assert len(ctx.items) == 1
    assert ctx.items[0].score == 0.9


def test_unique_chunks_all_included():
    package = _make_package_with_chunk_ids([
        ("e1", "chunk A content", 0.9, "chunk_A"),
        ("e2", "chunk B content", 0.8, "chunk_B"),
        ("e3", "chunk C content", 0.7, "chunk_C"),
    ])
    ctx = assemble_context(package)
    assert len(ctx.items) == 3


# ---------------------------------------------------------------------------
# Integrity Validation
# ---------------------------------------------------------------------------

def test_empty_content_item_is_dropped():
    package = _make_package([
        ("e1", "",    0.9),
        ("e2", "   ", 0.8),   # whitespace only
        ("e3", "valid content", 0.7),
    ])
    ctx = assemble_context(package)
    assert len(ctx.items) == 1
    assert ctx.items[0].evidence_id == "e3"


def test_items_dropped_count_includes_empty_items():
    package = _make_package([
        ("e1", "", 0.9),
        ("e2", "real content", 0.8),
    ])
    ctx = assemble_context(package)
    assert ctx.items_dropped == 1


# ---------------------------------------------------------------------------
# Context Policy — minimum score threshold
# ---------------------------------------------------------------------------

def test_low_or_negative_score_items_are_kept():
    # RRF scores (~0.03) and negative logits are normal; no absolute floor.
    package = _make_package([
        ("e1", "rrf scored evidence", 0.016),
        ("e2", "negative logit evidence", -2.5),
    ])
    ctx = assemble_context(package)
    assert [i.evidence_id for i in ctx.items] == ["e1", "e2"]


def test_last_item_is_compressed_when_room_is_left():
    package = _make_package([
        ("e1", "a" * 400, 0.9),
        ("e2", "b" * 2000, 0.8),
    ])
    ctx = assemble_context(package, budget_tokens=250)
    assert [i.evidence_id for i in ctx.items] == ["e1", "e2"]
    assert ctx.items[1].tokens <= 150
    assert ctx.total_tokens <= 250 and ctx.truncated


def test_identical_text_under_different_chunk_ids_is_deduplicated():
    package = _make_package([
        ("e1", "The rate limit is 100 requests per minute.", 0.9),
        ("e2", "The  rate limit is 100 requests per minute.", 0.8),
    ])
    ctx = assemble_context(package)
    assert [i.evidence_id for i in ctx.items] == ["e1"]
    assert ctx.items_dropped == 1


def test_items_dropped_zero_when_all_pass():
    package = _make_package([
        ("e1", "valid A", 0.9),
        ("e2", "valid B", 0.8),
    ])
    ctx = assemble_context(package)
    assert ctx.items_dropped == 0


def test_items_dropped_counts_budget_overflow():
    package = _make_package([
        ("e1", "a" * 400, 0.9),
        ("e2", "b" * 400, 0.8),
    ])
    ctx = assemble_context(package, budget_tokens=150)
    assert len(ctx.items) == 1
    assert ctx.items_dropped == 1   # cut by the budget, and reported


def test_conflicts_between_packed_items_become_notes():
    package = _make_package([
        ("e1", "Limit is 100 per minute.", 0.9),
        ("e2", "Limit is 1000 per minute.", 0.8),
    ])
    conflict = MagicMock()
    conflict.chunk_ids = ["chunk_e1", "chunk_e2"]
    conflict.reason = "different numbers (100 vs 1000)"
    package.conflicts = [conflict]
    ctx = assemble_context(package)
    assert ctx.conflict_notes == ["Evidence [1] and [2] disagree: different numbers (100 vs 1000)."]


