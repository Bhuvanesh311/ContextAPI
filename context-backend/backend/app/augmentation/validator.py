"""
L11 G6 / G7: output parsing & structural validation, grounding & citations.

G6  clean the text (strip <think> blocks and fences), reject empty output,
    cap the length, detect system-prompt leakage and abstentions.
G7  grounding is measured per claim, not per context item: a factual
    sentence is "supported" when it carries a valid [N] citation whose
    evidence actually contains most of the sentence's key words, or a valid
    [MN] memory citation. grounding_score = supported / factual sentences.
"""

import re
from typing import Dict, List, Set

from app.augmentation.prompt_builder import TRUSTED_MARKERS
from app.augmentation.schemas import AssembledContext, CitationRef, GeneratedAnswer, GenerationResult
from app.retrieval.textutil import sentences, term_coverage

MAX_ANSWER_CHARS = 8_000
SUPPORT_MIN_COVERAGE = 0.5      # share of a claim's key words found in its cited evidence
_MIN_CLAIM_WORDS = 4

_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
_EVIDENCE_CITE = re.compile(r"\[(\d+)\]")
_MEMORY_CITE = re.compile(r"\[M(\d+)\]", re.IGNORECASE)
_ANY_CITE = re.compile(r"\[(?:M)?\d+\]", re.IGNORECASE)
# "claim. [1][2]" -> "claim [1][2]." so a citation placed after the full stop
# stays with the sentence it supports when the text is split into claims.
_TRAILING_CITES = re.compile(r"([.!?])\s*((?:\[(?:M)?\d+\]\s*)+)", re.IGNORECASE)
_ABSTAIN = re.compile(
    r"\b(?:does not contain|doesn't contain|do not contain|not enough information|insufficient information|"
    r"no information|cannot be determined|can't be determined|not mentioned|not provided in the|"
    r"unable to (?:find|answer|determine)|i (?:do not|don't) know)\b",
    re.IGNORECASE,
)


def clean_output(text: str) -> str:
    text = _THINK.sub("", text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    return text[:MAX_ANSWER_CHARS]


def leaks_system_prompt(text: str) -> bool:
    return any(marker.lower() in text.lower() for marker in TRUSTED_MARKERS)


def validate(result: GenerationResult, context: AssembledContext, memory_count: int = 0) -> GeneratedAnswer:
    text = clean_output(result.text)
    base = dict(
        tokens_used=result.tokens_used,
        cost_used=result.cost_used,
        tier=result.tier,
        model=result.model,
        llm_calls=result.llm_calls,
    )
    if not text:
        return GeneratedAnswer(
            answer="",
            error_code=result.error_code or "EMPTY_OUTPUT",
            warnings=[result.error_message or "No answer generated."],
            **base,
        )

    warnings: List[str] = []
    if leaks_system_prompt(text):
        warnings.append("SYSTEM_PROMPT_LEAK: answer repeats trusted instructions.")

    item_by_rank = {item.rank: item for item in context.items}
    content_by_rank: Dict[int, str] = {item.rank: item.content for item in context.items}

    cited_numbers = [int(n) for n in _EVIDENCE_CITE.findall(text)]
    invalid: Set[int] = {n for n in cited_numbers if n not in item_by_rank}
    invalid_memory = {int(n) for n in _MEMORY_CITE.findall(text) if not 1 <= int(n) <= memory_count}
    for n in sorted(invalid):
        warnings.append(f"Citation [{n}] does not match any evidence block.")
    for n in sorted(invalid_memory):
        warnings.append(f"Citation [M{n}] does not match any memory item.")

    citations = [
        CitationRef(
            citation_number=n,
            evidence_id=item_by_rank[n].evidence_id,
            chunk_id=item_by_rank[n].chunk_id,
            document_id=item_by_rank[n].document_id,
            document_name=item_by_rank[n].document_name,
        )
        for n in sorted(set(cited_numbers) - invalid)
    ]

    factual = 0
    supported = 0
    abstain_sentences = 0
    claim_text = _TRAILING_CITES.sub(lambda m: f" {m.group(2).strip()}{m.group(1)} ", text)
    for sentence in sentences(claim_text) or [claim_text]:
        plain = _ANY_CITE.sub("", sentence).strip()
        if _ABSTAIN.search(plain):
            abstain_sentences += 1
            continue
        if len(plain.split()) < _MIN_CLAIM_WORDS:
            continue
        factual += 1
        refs = [int(n) for n in _EVIDENCE_CITE.findall(sentence) if int(n) in content_by_rank]
        mem_refs = [int(n) for n in _MEMORY_CITE.findall(sentence) if 1 <= int(n) <= memory_count]
        if refs:
            coverage, _, _ = term_coverage(plain, "\n".join(content_by_rank[r] for r in refs))
            if coverage >= SUPPORT_MIN_COVERAGE:
                supported += 1
        elif mem_refs:
            supported += 1

    abstained = abstain_sentences > 0 and factual == 0
    grounding = supported / factual if factual else 0.0

    if factual and grounding < 0.5:
        warnings.append(
            f"Only {supported} of {factual} claims are supported by their cited evidence."
        )

    return GeneratedAnswer(
        answer=text,
        citations=citations,
        grounding_score=round(grounding, 3),
        supported_claims=supported,
        factual_claims=factual,
        invalid_citations=sorted(invalid),
        abstained=abstained,
        warnings=warnings,
        **base,
    )
