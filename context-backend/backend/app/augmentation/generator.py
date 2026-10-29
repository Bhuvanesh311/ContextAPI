"""
L11 G1 / G3 / G5: input validation, model routing and execution.

G1  the prompt must fit the model context window and the caller's token budget.
G3  route: Tier B (local Ollama, no cost) first; Tier C (external) only for
    COLLABORATIVE, only when a real API key exists and the cost budget allows.
G5  every call is bounded by one generation deadline shared by all tiers and
    by the G8 repair; trusted instructions go in the system message.
"""

import logging
import time
from typing import Callable, Optional

from app.core.config import settings
from app.infra.ollama.config import ollama_config
from app.retrieval.security.profiles import ProfileControls
from app.retrieval.intelligence.providers.router import ModelProviderRouter
from app.augmentation.schemas import BuiltPrompt, GenerationResult

logger = logging.getLogger(__name__)

_ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

_TIER_C_COST_PER_TOKEN: float = 2e-6
_MIN_CALL_SECONDS = 2

_router: Optional[ModelProviderRouter] = None


def _get_router() -> ModelProviderRouter:
    global _router
    if _router is None:
        _router = ModelProviderRouter()
    return _router


def new_deadline() -> float:
    return time.monotonic() + settings.GENERATION_TIMEOUT_SECONDS


def _remaining(deadline: Optional[float]) -> float:
    if deadline is None:
        return float(settings.GENERATION_TIMEOUT_SECONDS)
    return deadline - time.monotonic()


def _answer_text(raw) -> str:
    text = raw.get("answer", "") if isinstance(raw, dict) else ""
    return text if isinstance(text, str) else ""


def generate(
    prompt: BuiltPrompt,
    controls: ProfileControls,
    budget_tokens: Optional[int] = None,
    budget_cost: Optional[float] = None,
    deadline: Optional[float] = None,
    on_text: Optional[Callable[[str], None]] = None,
) -> GenerationResult:
    """`on_text` receives the Tier B answer text so far while it is generated."""
    if not controls.allow_llm:
        return GenerationResult(tier="skipped")

    # ---- G1: input & contract validation --------------------------------
    max_output = ollama_config.num_predict
    if prompt.estimated_tokens + max_output > ollama_config.num_ctx:
        return GenerationResult(
            tier="failed", error_code="CONTEXT_TOO_LARGE",
            error_message=f"Prompt ({prompt.estimated_tokens} tokens) does not fit the model context window.",
        )
    if budget_tokens is not None and prompt.estimated_tokens + max_output > budget_tokens:
        return GenerationResult(
            tier="failed", error_code="BUDGET_EXHAUSTED",
            error_message=f"Token budget ({budget_tokens}) is too small for this prompt.",
        )

    router = _get_router()
    calls = 0
    errors: list[str] = []

    # ---- G3/G5: Tier B (local) ------------------------------------------
    remaining = _remaining(deadline)
    if remaining >= _MIN_CALL_SECONDS:
        calls += 1
        try:
            # Free text: the answer is prose, so no JSON grammar is needed
            # (Ollama's grammar sampler is also unreliable on some models).
            finish_reason: list[Optional[str]] = [None]

            def stream(text_so_far: str, done_reason: Optional[str]) -> None:
                if done_reason:
                    finish_reason[0] = done_reason
                if on_text is not None:
                    on_text(text_so_far)

            text = router.execute_tier_b_text(
                prompt.user_prompt, timeout=int(remaining), system=prompt.system_prompt, on_text=stream
            )
            text = text if isinstance(text, str) else ""
            if text.strip():
                tokens = prompt.estimated_tokens + max(1, len(text) // 4)
                return GenerationResult(
                    text=text, tokens_used=tokens, tier="B", model=ollama_config.model, llm_calls=calls,
                    truncated=finish_reason[0] == "length",
                )
            errors.append("Tier B returned an empty answer")
        except Exception as exc:
            logger.warning("L11 Tier B failed: %s", exc)
            errors.append(f"Tier B: {str(exc)[:200]}")

    # ---- G3/G5: Tier C (external) ---------------------------------------
    remaining = _remaining(deadline)
    est_cost = (prompt.estimated_tokens + max_output) * _TIER_C_COST_PER_TOKEN
    tier_c_allowed = (
        controls.max_llm_calls > 1
        and router.has_tier_c()
        and (budget_cost is None or est_cost <= budget_cost)
        and remaining >= _MIN_CALL_SECONDS
    )
    if tier_c_allowed:
        calls += 1
        try:
            raw = router.execute_tier_c(
                prompt.user_prompt, _ANSWER_SCHEMA, timeout=int(remaining),
                deadline=deadline, system=prompt.system_prompt,
            )
            text = _answer_text(raw)
            if text.strip():
                tokens = prompt.estimated_tokens + max(1, len(text) // 4)
                return GenerationResult(
                    text=text, tokens_used=tokens, cost_used=tokens * _TIER_C_COST_PER_TOKEN,
                    tier="C", model="external", llm_calls=calls,
                )
            errors.append("Tier C returned an empty answer")
        except Exception as exc:
            logger.warning("L11 Tier C failed: %s", exc)
            errors.append(f"Tier C: {str(exc)[:200]}")

    if _remaining(deadline) < _MIN_CALL_SECONDS and not errors:
        return GenerationResult(tier="failed", error_code="GENERATION_TIMEOUT",
                                error_message="Generation time budget exhausted.", llm_calls=calls)
    return GenerationResult(
        tier="failed", error_code="MODEL_UNAVAILABLE", llm_calls=calls,
        error_message="; ".join(errors) or "No model available for this profile.",
    )
