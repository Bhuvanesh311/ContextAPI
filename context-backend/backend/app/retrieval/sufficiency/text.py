"""
Small deterministic text helpers used by L07.

No LLM, no network, no database. The same input always gives the same
output, which is what makes sufficiency decisions reproducible and testable.
"""

import re
from typing import List, Tuple

# Shared with L5/L6 so every layer agrees on what counts as a topic word.
# Question words and instruction verbs are stopwords on purpose: "explain",
# "compare", "what" say HOW to answer, not WHAT the answer is about.
from app.retrieval.textutil import STOPWORDS

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def stem(token: str) -> str:
    """Very light stemmer. Only used to compare query words with evidence words."""
    t = token.lower()
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 5 and t.endswith("ing"):
        return t[:-3]
    if len(t) > 4 and t.endswith("ed"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        return t[:-1]
    return t


def significant_terms(text: str) -> List[Tuple[str, str]]:
    """
    Topic words of a text as (surface, stem) pairs, in order, unique by stem.

    "Explain the rate limiting of payments API" ->
        [("rate","rate"), ("limiting","limit"), ("payments","payment"), ("api","api")]
    """
    seen = set()
    result: List[Tuple[str, str]] = []
    for tok in tokens(text):
        if tok in STOPWORDS:
            continue
        if len(tok) < 2 and not tok.isdigit():
            continue
        st = stem(tok)
        if st in seen:
            continue
        seen.add(st)
        result.append((tok, st))
    return result