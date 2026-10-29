"""
L10 Generator tests.

Verifies profile gating, Tier B/C routing, and token/cost accounting.
Uses unittest.mock to avoid real LLM calls.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.enums import ExecutionProfile
from app.retrieval.security.profiles import controls_for
from app.augmentation.schemas import BuiltPrompt
from app.augmentation.generator import generate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prompt(tokens: int = 100) -> BuiltPrompt:
    return BuiltPrompt(
        system_prompt="You are helpful.",
        user_prompt="Question: What is X?",
        intent="FACT_LOOKUP",
        estimated_tokens=tokens,
    )


def _mock_router(tier_b_answer: str | None = "The answer.", tier_b_raises=False, tier_c_answer: str | None = None, tier_c_raises=False):
    router = MagicMock()
    if tier_b_raises:
        router.execute_tier_b_text.side_effect = RuntimeError("Ollama unavailable")
    else:
        router.execute_tier_b_text.return_value = tier_b_answer

    if tier_c_raises:
        router.execute_tier_c.side_effect = RuntimeError("All Tier C failed")
    else:
        router.execute_tier_c.return_value = {"answer": tier_c_answer or "Tier C answer"}
    return router


# ---------------------------------------------------------------------------
# Profile gating
# ---------------------------------------------------------------------------

def test_fast_profile_skips_generation():
    controls = controls_for(ExecutionProfile.FAST)
    result = generate(_prompt(), controls)
    assert result.tier == "skipped"
    assert result.text == ""
    assert result.tokens_used == 0


def test_standard_profile_skips_generation():
    controls = controls_for(ExecutionProfile.STANDARD)
    result = generate(_prompt(), controls)
    assert result.tier == "skipped"


# ---------------------------------------------------------------------------
# Tier B (DEEP)
# ---------------------------------------------------------------------------

def test_deep_profile_calls_tier_b():
    controls = controls_for(ExecutionProfile.DEEP)
    router = _mock_router(tier_b_answer="Rate limit is 100.")
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(), controls)
    assert result.tier == "B"
    assert result.text == "Rate limit is 100."
    assert result.tokens_used > 0
    assert result.cost_used == 0.0  # Tier B has no monetary cost


def test_deep_tier_b_failure_returns_failed_no_tier_c():
    controls = controls_for(ExecutionProfile.DEEP)  # max_llm_calls=1
    router = _mock_router(tier_b_raises=True)
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(), controls)
    assert result.tier == "failed"
    router.execute_tier_c.assert_not_called()


# ---------------------------------------------------------------------------
# Tier C (COLLABORATIVE)
# ---------------------------------------------------------------------------

def test_collaborative_falls_back_to_tier_c_on_tier_b_failure():
    controls = controls_for(ExecutionProfile.COLLABORATIVE)  # max_llm_calls=2
    router = _mock_router(tier_b_raises=True, tier_c_answer="Fallback answer.")
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(), controls)
    assert result.tier == "C"
    assert result.text == "Fallback answer."
    assert result.cost_used > 0.0  # Tier C incurs monetary cost


def test_collaborative_uses_tier_b_when_available():
    controls = controls_for(ExecutionProfile.COLLABORATIVE)
    router = _mock_router(tier_b_answer="Good answer.")
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(), controls)
    assert result.tier == "B"
    router.execute_tier_c.assert_not_called()


def test_collaborative_both_tiers_fail_returns_failed():
    controls = controls_for(ExecutionProfile.COLLABORATIVE)
    router = _mock_router(tier_b_raises=True, tier_c_raises=True)
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(), controls)
    assert result.tier == "failed"
    assert result.text == ""


# ---------------------------------------------------------------------------
# Token / cost accounting
# ---------------------------------------------------------------------------

def test_token_count_includes_prompt_tokens():
    controls = controls_for(ExecutionProfile.DEEP)
    router = _mock_router(tier_b_answer="Short.")
    prompt = _prompt(tokens=200)
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(prompt, controls)
    # tokens = prompt.estimated_tokens + response_tokens
    assert result.tokens_used >= 200


def test_tier_c_cost_nonzero():
    controls = controls_for(ExecutionProfile.COLLABORATIVE)
    router = _mock_router(tier_b_raises=True, tier_c_answer="x" * 400)
    with patch("app.augmentation.generator._get_router", return_value=router):
        result = generate(_prompt(tokens=100), controls)
    assert result.tier == "C"
    assert result.cost_used > 0.0
