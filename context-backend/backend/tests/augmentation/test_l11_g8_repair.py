"""L11 G8: at most one bounded repair; the better answer is kept."""

import time
from unittest.mock import patch

from app.augmentation.repair import REPAIR_THRESHOLD, attempt_repair, needs_repair
from app.augmentation.schemas import AssembledContext, BuiltPrompt, ContextItem, GeneratedAnswer, GenerationResult
from app.retrieval.security.profiles import controls_for
from app.core.enums import ExecutionProfile

DEEP = controls_for(ExecutionProfile.DEEP)
CTX = AssembledContext(items=[
    ContextItem(rank=1, evidence_id="ev1", content="Authentication uses a bearer token sent in the Authorization header.",
                document_id="D1", chunk_id="c1", score=1.0, tokens=20),
])
PROMPT = BuiltPrompt(system_prompt="SYS", user_prompt="USER", intent="FACT_LOOKUP", estimated_tokens=100)

GOOD_TEXT = "Authentication uses a bearer token sent in the Authorization header [1]."
WEAK = GeneratedAnswer(answer="Authentication uses API keys in the query string.", grounding_score=0.0,
                       factual_claims=1, tokens_used=100, llm_calls=1)


def test_needs_repair_rules():
    assert needs_repair(WEAK)
    assert not needs_repair(WEAK.model_copy(update={"grounding_score": REPAIR_THRESHOLD}))
    assert needs_repair(WEAK.model_copy(update={"grounding_score": 1.0, "invalid_citations": [7]}))
    assert not needs_repair(WEAK.model_copy(update={"abstained": True}))
    assert not needs_repair(GeneratedAnswer(answer=""))


def test_repair_is_skipped_when_time_is_short():
    with patch("app.augmentation.repair.generate") as gen:
        out = attempt_repair(WEAK, PROMPT, CTX, DEEP, deadline=time.monotonic() + 3)
    gen.assert_not_called()
    assert any("time budget" in w for w in out.warnings)


def test_repair_called_once_and_better_answer_kept():
    with patch("app.augmentation.repair.generate",
               return_value=GenerationResult(text=GOOD_TEXT, tokens_used=110, tier="B", llm_calls=1)) as gen:
        out = attempt_repair(WEAK, PROMPT, CTX, DEEP, deadline=time.monotonic() + 60)
    assert gen.call_count == 1
    assert out.answer == GOOD_TEXT and out.grounding_score == 1.0
    assert out.repair_attempted and out.llm_calls == 2 and out.tokens_used == 210
    repair_prompt = gen.call_args.args[0]
    assert "[REPAIR REQUEST]" in repair_prompt.user_prompt and repair_prompt.system_prompt == "SYS"


def test_worse_repair_keeps_original():
    with patch("app.augmentation.repair.generate",
               return_value=GenerationResult(text="", tier="failed", llm_calls=1)):
        out = attempt_repair(WEAK, PROMPT, CTX, DEEP, deadline=time.monotonic() + 60)
    assert out.answer == WEAK.answer and out.repair_attempted
    assert any("original kept" in w for w in out.warnings)


def test_repair_shares_token_budget():
    with patch("app.augmentation.repair.generate",
               return_value=GenerationResult(text=GOOD_TEXT, llm_calls=1)) as gen:
        attempt_repair(WEAK, PROMPT, CTX, DEEP, deadline=time.monotonic() + 60, budget_tokens=1000, budget_cost=0.5)
    assert gen.call_args.args[2] == 900       # tokens left after the first call
