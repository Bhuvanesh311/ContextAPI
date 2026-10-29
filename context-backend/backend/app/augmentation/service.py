"""
Augmentation pipeline: L8 memory (loaded by the caller) -> L9 -> L10 -> L11 (G1-G9).

G2  policy: FAST / STANDARD never generate (SKIPPED); evidence that L07
    judged INSUFFICIENT is never sent to a model (INSUFFICIENT_CONTEXT), so
    the model cannot "answer" from irrelevant text. Output mode follows the
    caller: "answer" for users, "structured" for agents / planners / workflows.
G9  finalisation: one status per answer —
      SUCCESS               grounded answer (>= threshold) from SUFFICIENT evidence
      PARTIAL               answer exists but evidence or grounding is incomplete
      INSUFFICIENT_CONTEXT  no usable evidence, or the model said it cannot answer
      FAILED                model unavailable, budget / time exhausted, unsafe output
      CANCELLED             request cancelled before generation
      SKIPPED               profile does not generate
"""

import logging
import time
from typing import Callable, Optional, TYPE_CHECKING

from app.core.config import settings
from app.core.enums import QueryIntent, RequestSourceType
from app.infra.ollama.config import ollama_config
from app.retrieval.evidence.package import EvidencePackage
from app.retrieval.security.profiles import ProfileControls
from app.augmentation.context_assembly import assemble_context
from app.augmentation.prompt_builder import build_prompt
from app.augmentation.generator import generate, new_deadline
from app.augmentation.validator import leaks_system_prompt, validate
from app.augmentation.repair import REPAIR_THRESHOLD, attempt_repair
from app.augmentation.schemas import GeneratedAnswer, GenerationStatus

if TYPE_CHECKING:
    from app.augmentation.memory.schemas import RelevantMemoryPackage

logger = logging.getLogger(__name__)

_PROMPT_OVERHEAD_TOKENS = 1_500   # system prompt + memory + question + notes
_AGENT_SOURCES = {RequestSourceType.AGENT, RequestSourceType.PLANNER_AGENT, RequestSourceType.WORKFLOW}


def _context_budget(budget_tokens_remaining: Optional[int]) -> int:
    window = ollama_config.num_ctx - ollama_config.num_predict - _PROMPT_OVERHEAD_TOKENS
    budget = max(500, min(settings.GENERATION_CONTEXT_TOKENS, window))
    if budget_tokens_remaining is not None:
        budget = min(budget, max(0, budget_tokens_remaining - ollama_config.num_predict - _PROMPT_OVERHEAD_TOKENS))
    return budget


def run_augmentation(
    package: EvidencePackage,
    query: str,
    intent: QueryIntent,
    controls: ProfileControls,
    budget_tokens_remaining: Optional[int] = None,
    budget_cost_remaining: Optional[float] = None,
    memory_package: "Optional[RelevantMemoryPackage]" = None,
    source_type: Optional[RequestSourceType] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    on_text: Optional[Callable[[str], None]] = None,
) -> GeneratedAnswer:
    started = time.monotonic()
    output_mode = "structured" if source_type in _AGENT_SOURCES else "answer"
    verdict = getattr(package, "verdict", None)

    def finish(answer: GeneratedAnswer) -> GeneratedAnswer:
        return answer.model_copy(update={
            "output_mode": output_mode,
            "evidence_verdict": verdict,
            "latency_ms": int((time.monotonic() - started) * 1000),
        })

    # ---- G2: output mode & policy resolution ----------------------------
    if not controls.allow_llm:
        return finish(GeneratedAnswer(
            status=GenerationStatus.SKIPPED, skipped=True,
            skip_reason="Profile does not allow LLM generation.",
        ))
    if is_cancelled is not None and is_cancelled():
        return finish(GeneratedAnswer(status=GenerationStatus.CANCELLED, skip_reason="Request was cancelled."))
    if not package.evidence or verdict == "INSUFFICIENT":
        return finish(GeneratedAnswer(
            status=GenerationStatus.INSUFFICIENT_CONTEXT,
            skip_reason="Retrieved evidence is not sufficient to answer; no model was called.",
            warnings=[g.message for g in getattr(package, "unresolved_gaps", [])][:5],
        ))

    # ---- L9: context / token / compression ------------------------------
    context_budget = _context_budget(budget_tokens_remaining)
    if context_budget < 100:
        return finish(GeneratedAnswer(
            status=GenerationStatus.FAILED, error_code="BUDGET_EXHAUSTED",
            warnings=["Token budget left after retrieval is too small to generate an answer."],
        ))
    context = assemble_context(package, budget_tokens=context_budget)
    if not context.items:
        return finish(GeneratedAnswer(
            status=GenerationStatus.INSUFFICIENT_CONTEXT,
            skip_reason="No usable evidence after context assembly.",
        ))

    # ---- L10: prompt & model context assembly ---------------------------
    prompt = build_prompt(query, intent, context, memory_package=memory_package)

    # ---- L11: G1/G3/G5 generate, G6/G7 validate, G8 repair --------------
    deadline = new_deadline()

    def stream(text: str) -> None:
        # Live text skips G6-G9, so at least never show a system-prompt leak.
        if on_text is not None and not leaks_system_prompt(text):
            on_text(text)

    result = generate(
        prompt, controls, budget_tokens_remaining, budget_cost_remaining, deadline=deadline, on_text=stream,
    )
    if not result.text:
        return finish(GeneratedAnswer(
            status=GenerationStatus.FAILED,
            error_code=result.error_code or "MODEL_UNAVAILABLE",
            warnings=[result.error_message or "Generation failed."],
            llm_calls=result.llm_calls, tier=result.tier,
        ))

    answer = validate(result, context, memory_count=prompt.memory_count)
    if settings.GENERATION_REPAIR_ENABLED:
        answer = attempt_repair(
            answer, prompt, context, controls,
            deadline=deadline, budget_tokens=budget_tokens_remaining, budget_cost=budget_cost_remaining,
        )
    if result.truncated:
        answer = answer.model_copy(update={
            "warnings": answer.warnings + ["The answer reached the length limit and may be cut short."],
        })
    if context.truncated:
        answer = answer.model_copy(update={"warnings": answer.warnings + ["Context was truncated to fit the budget."]})
    if context.conflict_notes:
        answer = answer.model_copy(update={"warnings": answer.warnings + context.conflict_notes})

    # ---- G9: finalisation & response packaging --------------------------
    if leaks_system_prompt(answer.answer):
        return finish(answer.model_copy(update={
            "status": GenerationStatus.FAILED, "error_code": "UNSAFE_OUTPUT", "answer": "",
            "citations": [],
        }))
    if answer.abstained:
        status = GenerationStatus.INSUFFICIENT_CONTEXT
    elif (
        answer.grounding_score >= REPAIR_THRESHOLD
        and not answer.invalid_citations
        and verdict == "SUFFICIENT"
    ):
        status = GenerationStatus.SUCCESS
    else:
        status = GenerationStatus.PARTIAL
    return finish(answer.model_copy(update={"status": status}))
