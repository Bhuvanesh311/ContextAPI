"""
L9 Prompt Engineering tests.

Verifies that build_prompt() produces intent-specific prompts and correctly
embeds numbered context blocks.
"""

import pytest
from unittest.mock import MagicMock

from app.core.enums import QueryIntent
from app.augmentation.prompt_builder import build_prompt
from app.augmentation.schemas import AssembledContext, ContextItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _item(rank: int, content: str, doc_name: str = "doc.pdf") -> ContextItem:
    return ContextItem(
        rank=rank,
        evidence_id=f"ev{rank}",
        content=content,
        document_id="DOC1",
        document_name=doc_name,
        chunk_id=f"chunk{rank}",
        score=0.9,
        tokens=len(content) // 4 or 1,
    )


def _context(*contents: str) -> AssembledContext:
    items = [_item(i + 1, c) for i, c in enumerate(contents)]
    return AssembledContext(items=items, total_tokens=sum(i.tokens for i in items), budget_tokens=3000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fact_lookup_instruction_in_system_prompt():
    ctx = _context("The rate limit is 100 req/s.")
    prompt = build_prompt("What is the rate limit?", QueryIntent.FACT_LOOKUP, ctx)
    assert "direct" in prompt.system_prompt.lower() or "concise" in prompt.system_prompt.lower()


def test_explanation_instruction_differs_from_fact_lookup():
    ctx = _context("Auth uses JWT tokens.")
    p1 = build_prompt("What is JWT?", QueryIntent.EXPLANATION, ctx)
    p2 = build_prompt("What is JWT?", QueryIntent.FACT_LOOKUP, ctx)
    assert p1.system_prompt != p2.system_prompt


def test_comparison_instruction_mentions_compare():
    ctx = _context("Option A does X.", "Option B does Y.")
    prompt = build_prompt("Compare A and B.", QueryIntent.COMPARISON, ctx)
    assert "compar" in prompt.system_prompt.lower()


def test_context_blocks_numbered_correctly():
    ctx = _context("First chunk.", "Second chunk.", "Third chunk.")
    prompt = build_prompt("Query", QueryIntent.FACT_LOOKUP, ctx)
    assert "[1]" in prompt.user_prompt
    assert "[2]" in prompt.user_prompt
    assert "[3]" in prompt.user_prompt


def test_query_present_in_user_prompt():
    ctx = _context("Some context.")
    prompt = build_prompt("What is InferAI?", QueryIntent.FACT_LOOKUP, ctx)
    assert "What is InferAI?" in prompt.user_prompt


def test_document_name_used_as_source_label():
    item = _item(1, "content here", doc_name="myfile.pdf")
    ctx = AssembledContext(items=[item], total_tokens=10, budget_tokens=3000)
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "myfile.pdf" in prompt.user_prompt


def test_empty_context_shows_no_context_message():
    ctx = AssembledContext(items=[], total_tokens=0, budget_tokens=3000)
    prompt = build_prompt("Any question", QueryIntent.UNKNOWN, ctx)
    assert "No context available" in prompt.user_prompt


def test_estimated_tokens_positive():
    ctx = _context("Some content about the topic.")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert prompt.estimated_tokens > 0


def test_intent_field_matches_enum_value():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.ANALYSIS, ctx)
    assert prompt.intent == QueryIntent.ANALYSIS.value


def test_cite_instruction_always_present():
    for intent in [QueryIntent.FACT_LOOKUP, QueryIntent.EXPLANATION, QueryIntent.COMPARISON]:
        ctx = _context("content")
        prompt = build_prompt("Q", intent, ctx)
        assert "[N]" in prompt.system_prompt or "cite" in prompt.system_prompt.lower()


# ---------------------------------------------------------------------------
# Trust boundary
# ---------------------------------------------------------------------------

def test_evidence_wrapped_in_fences():
    ctx = _context("sensitive document content here")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "<evidence>" in prompt.user_prompt
    assert "</evidence>" in prompt.user_prompt


def test_memory_wrapped_in_fences():
    from app.augmentation.memory.schemas import MemoryItem, RelevantMemoryPackage, MemorySourceType

    mem_item = MemoryItem(
        item_id="s0", source_type=MemorySourceType.SESSION,
        content="Q: previous question A: previous answer",
        relevance_score=0.8, priority_score=0.6,
    )
    pkg = RelevantMemoryPackage(session_items=[mem_item], total_items=1, total_tokens=10)
    ctx = _context("some evidence")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx, memory_package=pkg)
    assert "<memory>" in prompt.user_prompt
    assert "</memory>" in prompt.user_prompt


def test_instructions_only_in_system_prompt():
    """Instructions must never appear inside evidence or memory data blocks."""
    ctx = _context("evidence content")
    prompt = build_prompt("What is X?", QueryIntent.FACT_LOOKUP, ctx)
    # The instruction keyword appears in system_prompt
    assert "direct" in prompt.system_prompt.lower() or "concise" in prompt.system_prompt.lower()
    # Evidence fence contains only evidence, not instructions
    ev_start = prompt.user_prompt.index("<evidence>")
    ev_end   = prompt.user_prompt.index("</evidence>")
    evidence_block = prompt.user_prompt[ev_start:ev_end]
    assert "Instruction:" not in evidence_block


# ---------------------------------------------------------------------------
# Truncation notice
# ---------------------------------------------------------------------------

def test_truncation_notice_when_context_truncated():
    ctx = AssembledContext(
        items=[_item(1, "some content")],
        total_tokens=10,
        budget_tokens=3000,
        truncated=True,
    )
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "truncated" in prompt.user_prompt.lower()


def test_no_truncation_notice_when_not_truncated():
    ctx = AssembledContext(
        items=[_item(1, "some content")],
        total_tokens=10,
        budget_tokens=3000,
        truncated=False,
    )
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "truncated" not in prompt.user_prompt.lower()


# ---------------------------------------------------------------------------
# Safety Policy (L10 trusted instruction)
# ---------------------------------------------------------------------------

def test_safety_policy_present_in_system_prompt():
    ctx = _context("evidence content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    sp = prompt.system_prompt.lower()
    assert "untrusted" in sp or "do not follow" in sp or "safety" in sp


def test_safety_policy_warns_against_embedded_instructions():
    ctx = _context("evidence content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    # Safety policy should mention instructions/directives in evidence are to be ignored
    assert "instructions" in prompt.system_prompt.lower() or "directives" in prompt.system_prompt.lower()


# ---------------------------------------------------------------------------
# Output Contract (L10 trusted instruction)
# ---------------------------------------------------------------------------

def test_output_contract_present_in_system_prompt():
    ctx = _context("evidence content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    sp = prompt.system_prompt.lower()
    assert "output contract" in sp or "cite" in sp


def test_output_contract_specifies_citation_format():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    # A concrete example, not an "[N]" placeholder: small models copied the placeholder verbatim.
    assert "[1]" in prompt.system_prompt
    assert "[N]" not in prompt.system_prompt


def test_all_trusted_sections_in_system_prompt():
    """System Policy, Safety Policy, Task, Constraints, Output Contract all present."""
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.ANALYSIS, ctx)
    sp = prompt.system_prompt.lower()
    assert "factual" in sp or "precise" in sp          # system policy
    assert "untrusted" in sp or "safety" in sp          # safety policy
    assert "analys" in sp                               # task instruction
    assert "constraints" in sp                          # constraints
    assert "output contract" in sp or "cite" in sp      # output contract


# ---------------------------------------------------------------------------
# Constraints (L10 trusted instruction)
# ---------------------------------------------------------------------------

def test_constraints_section_present_in_system_prompt():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "CONSTRAINTS" in prompt.system_prompt


def test_constraints_includes_scope():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "scope" in prompt.system_prompt.lower() or "outside" in prompt.system_prompt.lower()


def test_constraints_includes_confidentiality():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "confidential" in prompt.system_prompt.lower() or "expose" in prompt.system_prompt.lower()


def test_constraints_includes_language():
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    assert "language" in prompt.system_prompt.lower()


def test_five_trusted_sections_ordering():
    """System Policy → Safety → Task → Constraints → Output Contract, all in order."""
    ctx = _context("content")
    prompt = build_prompt("Q", QueryIntent.FACT_LOOKUP, ctx)
    sp = prompt.system_prompt
    idx_safety   = sp.index("SAFETY")
    idx_task     = sp.index("TASK")
    idx_const    = sp.index("CONSTRAINTS")
    idx_contract = sp.index("OUTPUT CONTRACT")
    assert idx_safety < idx_task < idx_const < idx_contract


def test_overview_question_asks_for_a_summary_of_the_evidence():
    # "full details about pdf" names the document, not a topic: summarise its content.
    ctx = _context("ContextAPI reconstructs API documentation.")
    prompt = build_prompt("full details about pdf?", QueryIntent.UNKNOWN, ctx)
    assert "overview" in prompt.system_prompt.lower()


def test_topic_question_does_not_get_overview_instruction():
    ctx = _context("The rate limit is 100 req/s.")
    prompt = build_prompt("full details about the rate limit", QueryIntent.FACT_LOOKUP, ctx)
    assert "overview of the documents" not in prompt.system_prompt


def test_overview_question_says_the_evidence_is_the_document():
    # Without this, a 4B model answered "the context has no PDF metadata" and refused.
    prompt = build_prompt("full details about pdf?", QueryIntent.UNKNOWN, _context("ContextAPI overview."))
    assert "Interpretation:" in prompt.user_prompt
    assert "Interpretation:" not in build_prompt("What is JWT?", QueryIntent.FACT_LOOKUP, _context("x")).user_prompt


def test_partial_evidence_is_answered_not_refused():
    # A 4B model refused "how to start a project" although block [1] had the steps;
    # the contract must ask for a partial answer and refuse only when nothing is relevant.
    prompt = build_prompt("how to start a project?", QueryIntent.EXPLANATION, _context("POST /projects/ creates a project."))
    assert "PARTIAL EVIDENCE" in prompt.system_prompt
    assert "ONLY when no evidence block is relevant" in prompt.system_prompt


def test_informal_tamil_english_questions_are_explained_to_the_model():
    # "leave pathi full details kudu" was read as a corrupted query and half-refused.
    prompt = build_prompt("leave pathi full details kudu", QueryIntent.UNKNOWN, _context("24 days of leave."))
    assert "'pathi' = about" in prompt.system_prompt
    assert "everything the evidence says about that topic" in prompt.system_prompt
