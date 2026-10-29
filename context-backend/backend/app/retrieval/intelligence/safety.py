import re
from typing import List, Pattern, Tuple

from app.core.enums import QuerySafetyOutcome
from app.retrieval.intelligence.schemas import QuerySafetyAssessment

# Blocks need an explicit *intent* (extract, override, reveal), not just a
# sensitive topic. This is an API-docs product: "what is a system prompt",
# "print the password policy" and "show me the api key format" are normal
# questions and must pass.

_SECRET = r"(?:api[\s_\-]?keys?|access[\s_\-]?tokens?|bearer\s+tokens?|passwords?|secrets?|credentials?|private[\s_\-]?keys?)"

# Words that turn a secret noun into a question *about* it, e.g. "password
# policy", "api key format", "secret rotation".
_ABOUT = (
    r"(?:policy|policies|format|formats|rotation|requirements?|rules?|length|reset|"
    r"field|header|headers|parameter|parameters|param|scheme|validation|strength|"
    r"complexity|expiry|expiration|lifetime|management|best\s+practices?|example|"
    r"examples|placeholder|naming|type|types|limit|limits|endpoint|flow|docs?|documentation)"
)

_BLOCK_RULES: List[Tuple[str, Pattern[str]]] = [
    ("PROMPT_INJECTION", re.compile(
        r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+)?"
        r"(?:previous|prior|above|earlier|system)\s+(?:instructions|prompts?|rules)\b",
        re.IGNORECASE,
    )),
    ("PROMPT_INJECTION", re.compile(
        r"\b(?:reveal|print|repeat|output|disclose|show|display|leak|dump)\s+(?:me\s+)?"
        r"(?:your|the|this)\s+(?:hidden\s+|full\s+|original\s+)?(?:system\s+prompt|system\s+instructions|initial\s+instructions)\b",
        re.IGNORECASE,
    )),
    ("POLICY_BYPASS", re.compile(r"\bbypass\s+(?:the\s+|your\s+)?(?:safety|content|security)?\s*polic(?:y|ies)\b", re.IGNORECASE)),
    ("JAILBREAK_ATTEMPT", re.compile(r"\b(?:jailbreak|DAN\s+mode|developer\s+mode\s+enabled)\b", re.IGNORECASE)),
    # Strong exfiltration verbs: no legitimate docs question needs them.
    ("CREDENTIAL_EXTRACTION", re.compile(
        rf"\b(?:dump|exfiltrate|steal|leak|harvest|scrape)\b.{{0,40}}\b{_SECRET}\b",
        re.IGNORECASE,
    )),
    # Weak verbs only block when they target actual secret values
    # ("give me all passwords", "print the api keys of user X"), not a topic
    # about them ("print the password policy").
    ("CREDENTIAL_EXTRACTION", re.compile(
        rf"\b(?:give|send|show|print|reveal|expose|list|tell)\s+(?:me\s+)?(?:(?:the|all|every|any|their|his|her|other)\s+)?"
        rf"(?:(?:real|actual|live|stored|production|user'?s?|users'?|admin)\s+)?{_SECRET}\b(?!\s+{_ABOUT}\b)",
        re.IGNORECASE,
    )),
]


def analyze_safety(query: str) -> QuerySafetyAssessment:
    if not query:
        return QuerySafetyAssessment(
            outcome=QuerySafetyOutcome.SAFE,
            risk_level=0.0,
            confidence=1.0,
            reasons=["Empty query"],
            categories=[],
        )

    reasons: List[str] = []
    categories: List[str] = []
    highest_risk = 0.0
    outcome = QuerySafetyOutcome.SAFE

    for label, pattern in _BLOCK_RULES:
        if pattern.search(query):
            reasons.append(f"Query blocked: {label}")
            if label not in categories:
                categories.append(label)
            highest_risk = max(highest_risk, 0.9)
            outcome = QuerySafetyOutcome.BLOCKED

    return QuerySafetyAssessment(
        outcome=outcome,
        risk_level=highest_risk,
        confidence=0.8,
        reasons=reasons,
        categories=categories,
    )
