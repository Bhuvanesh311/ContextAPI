"""
Small deterministic text helpers shared by L5 (rerank), L6 (evidence) and L3.

No LLM, no network, no database, no third-party imports: the same input
always gives the same output, so ranking and validation stay reproducible
and the module can be unit-tested anywhere.
"""

import re
import unicodedata
from typing import FrozenSet, List, Set, Tuple

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Words that point at the documents themselves rather than a topic:
# "full details about the pdf", "summary of this document". The answer is in
# the documents, but these words usually are not, so counting them as topic
# words made overview questions look unanswerable.
DOCUMENT_REFERENCE_WORDS: FrozenSet[str] = frozenset(
    """
    detail details full complete entire whole overall overview summary summarize
    summarise brief briefly everything info information content contents
    pdf pdfs doc docs document documents file files uploaded
    """.split()
)

STOPWORDS: FrozenSet[str] = frozenset(
    """
    a about above after again all also am an and any are as at be because been
    before being below between both but by can could did do does doing done down
    during each few for from further had has have having he her here hers him his
    how i if in into is it its just me more most my no nor not now of off on once
    only or other our out over own s same she should so some such t than that the
    their them then there these they this those through to too under until up us
    very was we were what when where which while who whom why will with would you
    your tell explain describe give show find list please compare difference
    differences mean means work works working worked
    """.split()
) | DOCUMENT_REFERENCE_WORDS | frozenset(
    # Common Tamil-in-English filler ("project pathi full details kudu").
    """
    kudu kudunga sollu sollunga pathi patthi enna yenna venum vendum da pa
    """.split()
)


NEGATIONS: FrozenSet[str] = frozenset(
    "not no never cannot cant dont doesnt isnt arent wont without disabled deprecated unsupported prohibited forbidden".split()
)


def clean_text(text: str) -> str:
    """NFKC-normalise, drop control characters, collapse whitespace."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = _CONTROL_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def stem(token: str) -> str:
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
    """Topic words as (surface, stem) pairs, in order, unique by stem."""
    seen: Set[str] = set()
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


def is_overview_question(text: str) -> bool:
    """True when the question names the documents but no topic in them."""
    words = set(tokens(text))
    return bool(words & DOCUMENT_REFERENCE_WORDS) and not significant_terms(text)


def stem_set(text: str) -> Set[str]:
    return {stem(t) for t in tokens(text)}


def term_coverage(query: str, content: str) -> Tuple[float, List[str], List[str]]:
    """Share of the query's topic words that appear in content (by stem)."""
    terms = significant_terms(query)
    if not terms:
        return 1.0, [], []
    present = stem_set(content)
    covered = [s for _, s in terms if s in present]
    missing = [s for _, s in terms if s not in present]
    return len(covered) / len(terms), covered, missing


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def numbers(text: str) -> Set[str]:
    return {n.replace(",", "") for n in _NUMBER_RE.findall(text or "")}


def sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text or "") if len(s.strip()) > 10]


def negation_count(text: str) -> int:
    return sum(1 for t in tokens(text.replace("'", "")) if t in NEGATIONS)