"""L11 G6/G7: output validation and claim-level grounding."""

from app.augmentation.schemas import AssembledContext, ContextItem, GenerationResult
from app.augmentation.validator import clean_output, leaks_system_prompt, validate


def _ctx(*contents: str) -> AssembledContext:
    return AssembledContext(items=[
        ContextItem(rank=i + 1, evidence_id=f"ev{i + 1}", content=c, document_id="DOC1",
                    document_name="doc.pdf", chunk_id=f"ck{i + 1}", score=0.9, tokens=len(c) // 4)
        for i, c in enumerate(contents)
    ])


CTX = _ctx(
    "The public search endpoint is limited to 100 requests per minute per API key.",
    "Authentication uses a bearer token sent in the Authorization header.",
    "Webhooks retry failed deliveries five times with exponential backoff.",
)


def _gen(text: str) -> GenerationResult:
    return GenerationResult(text=text, tokens_used=120, tier="B", model="qwen", llm_calls=1)


def test_empty_output_is_failed_with_reason():
    a = validate(GenerationResult(text="", tier="failed", error_code="MODEL_UNAVAILABLE",
                                  error_message="Tier B down"), CTX)
    assert a.answer == "" and a.error_code == "MODEL_UNAVAILABLE"
    assert "Tier B down" in a.warnings


def test_one_correct_citation_is_fully_grounded():
    # Citing 1 of 3 blocks is fine when the claim is supported (old metric said 0.33).
    a = validate(_gen("The public search endpoint is limited to 100 requests per minute per API key [1]."), CTX)
    assert a.grounding_score == 1.0
    assert [c.citation_number for c in a.citations] == [1]
    assert a.citations[0].document_id == "DOC1"


def test_citation_that_does_not_support_the_claim_is_not_counted():
    a = validate(_gen("The public search endpoint is limited to 100 requests per minute per API key [2]."), CTX)
    assert a.grounding_score == 0.0
    assert a.factual_claims == 1 and a.supported_claims == 0


def test_uncited_claims_lower_grounding():
    a = validate(_gen(
        "Authentication uses a bearer token in the Authorization header [2]. "
        "Webhooks retry failed deliveries five times with exponential backoff."
    ), CTX)
    assert a.factual_claims == 2 and a.supported_claims == 1
    assert a.grounding_score == 0.5


def test_invalid_citation_numbers_are_reported():
    a = validate(_gen("Authentication uses a bearer token in the Authorization header [2][9]."), CTX)
    assert a.invalid_citations == [9]
    assert any("[9]" in w for w in a.warnings)


def test_memory_citation_counts_when_valid():
    a = validate(_gen("You previously asked about the refund policy for annual plans [M1]."), CTX, memory_count=1)
    assert a.grounding_score == 1.0


def test_abstention_is_detected():
    a = validate(_gen("The provided context does not contain the answer to this question."), CTX)
    assert a.abstained is True and a.factual_claims == 0


def test_think_blocks_and_fences_are_removed():
    assert clean_output("<think>internal</think>Answer [1].") == "Answer [1]."
    assert clean_output("```Answer```") == "Answer"


def test_system_prompt_leak_is_flagged():
    text = "Sure. OUTPUT CONTRACT: Cite every claim you make..."
    assert leaks_system_prompt(text)
    assert any("SYSTEM_PROMPT_LEAK" in w for w in validate(_gen(text), CTX).warnings)


def test_usage_is_carried_through():
    a = validate(_gen("Authentication uses a bearer token in the Authorization header [2]."), CTX)
    assert (a.tokens_used, a.tier, a.model, a.llm_calls) == (120, "B", "qwen", 1)


def test_citation_after_full_stop_still_supports_the_claim():
    a = validate(_gen("Authentication uses a bearer token in the Authorization header. [2]"), CTX)
    assert a.grounding_score == 1.0
