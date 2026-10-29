"""
Deterministic contradiction detection between two evidence texts (L06).

Two sentences are "about the same statement" when they share most of their
content words. If those matching statements then disagree on a number, or one
negates what the other affirms, the two texts conflict.

It is a heuristic (no model), tuned to avoid false alarms:
  * it compares sentence against sentence, never whole chunks,
  * it ignores short sentences,
  * it needs a high word overlap before it says anything,
  * list/section numbers ("Step 1", "Section 2", "Figure 3") are not facts
    and are ignored,
  * statements that each carry their own qualifier ("free plan" vs "pro
    plan") describe different subjects and never conflict.
"""

import re
from typing import Optional, Set

from app.retrieval.textutil import (
    STOPWORDS,
    jaccard,
    negation_count,
    numbers,
    sentences,
    stem,
    tokens,
)

SAME_STATEMENT_JACCARD = 0.6      # negation check
SAME_NUMBER_STATEMENT_JACCARD = 0.75   # number check needs a closer match
MIN_CONTENT_WORDS = 3

_ORDINAL_RE = re.compile(
    r"\b(step|steps|section|chapter|page|figure|fig|table|item|part|phase|stage|rule|point|line)\s*\.?\s*\d+(?:\.\d+)*",
    re.IGNORECASE,
)
_LEADING_NUMBER_RE = re.compile(r"^\s*\(?\d+[.)]\s+")


def _content_words(sentence: str) -> Set[str]:
    return {
        stem(t)
        for t in tokens(sentence)
        if not t.isdigit() and t not in STOPWORDS
    }


def _facts_numbers(sentence: str) -> Set[str]:
    cleaned = _LEADING_NUMBER_RE.sub("", sentence)
    cleaned = _ORDINAL_RE.sub(" ", cleaned)
    return numbers(cleaned)


def find_contradiction(text_a: str, text_b: str) -> Optional[str]:
    """Return a short reason when the texts contradict each other, else None."""
    sents_a = [(s, _content_words(s)) for s in sentences(text_a)]
    sents_b = [(s, _content_words(s)) for s in sentences(text_b)]

    for sa, wa in sents_a:
        if len(wa) < MIN_CONTENT_WORDS:
            continue
        for sb, wb in sents_b:
            if len(wb) < MIN_CONTENT_WORDS:
                continue
            overlap = jaccard(wa, wb)
            if overlap < SAME_STATEMENT_JACCARD:
                continue
            # Each side has a word the other lacks ("free plan ... 100" vs
            # "pro plan ... 1000"): two statements about different subjects,
            # not one statement with two values.
            if (wa - wb) and (wb - wa):
                continue

            if overlap >= SAME_NUMBER_STATEMENT_JACCARD:
                na, nb = _facts_numbers(sa), _facts_numbers(sb)
                if na and nb and na != nb:
                    return (
                        "matching statements give different numbers "
                        f"({', '.join(sorted(na))} vs {', '.join(sorted(nb))})"
                    )

            if (negation_count(sa) == 0) != (negation_count(sb) == 0):
                return "matching statements disagree (one negates the other)"
    return None