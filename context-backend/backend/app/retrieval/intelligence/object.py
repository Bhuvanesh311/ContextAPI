"""
L03 deterministic object extraction (no model).

Pulls the things an API-docs question is usually about: endpoints, HTTP
methods, status codes, quoted phrases, code identifiers and versions, plus
standard identifiers and time references. Relationship extraction is not
implemented (relationship expansion / Neo4j is not deployed), so
`relationships` stays empty.
"""

import re
from typing import List

from app.retrieval.intelligence.schemas import ObjectIntelligence

UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
# Prefixed sequential ids used across the system (PROJ000007, DOCV000012, ...).
PREFIXED_ID_PATTERN = re.compile(r"\b[A-Z]{2,6}\d{4,}\b")
DATE_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
TEMPORAL_KEYWORDS = ["yesterday", "today", "tomorrow", "last week", "next month", "recently", "latest", "deprecated"]

_METHOD_PATH = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[\w\-./{}:]*)", re.IGNORECASE)
_PATH = re.compile(r"(?<![\w.])/(?:[\w\-{}:.]+/?)+")
_STATUS_CODE = re.compile(r"\b(?:HTTP\s*)?([1-5]\d{2})\b(?=\s*(?:error|status|response|code|ok|created|unauthorized|forbidden|not found)?)", re.IGNORECASE)
_QUOTED = re.compile(r"[\"“']([^\"”']{2,80})[\"”']")
_BACKTICK = re.compile(r"`([^`]{1,80})`")
_CODE_IDENT = re.compile(r"\b(?:[a-z]+(?:_[a-z0-9]+)+|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[a-z]+(?:[A-Z][a-z0-9]+)+|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+)\b")
_VERSION = re.compile(r"\bv\d+(?:\.\d+)*\b", re.IGNORECASE)


def _ordered_unique(items: List[str]) -> List[str]:
    return list(dict.fromkeys(i.strip() for i in items if i and i.strip()))


def _status_codes(query: str) -> List[str]:
    # Only treat a 3-digit number as a status code when it looks like one.
    return [m.group(1) for m in _STATUS_CODE.finditer(query) if re.search(r"\b(http|status|error|response|code)\b", query, re.IGNORECASE)]


def analyze_objects(query: str) -> ObjectIntelligence:
    if not query:
        return ObjectIntelligence()

    entities: List[str] = []
    for method, path in _METHOD_PATH.findall(query):
        entities.append(f"{method.upper()} {path}")
    entities.extend(_PATH.findall(query))
    entities.extend(_QUOTED.findall(query))
    entities.extend(_BACKTICK.findall(query))
    entities.extend(_CODE_IDENT.findall(query))
    entities.extend(_VERSION.findall(query))
    entities.extend(f"HTTP {code}" for code in _status_codes(query))

    identifiers = UUID_PATTERN.findall(query) + PREFIXED_ID_PATTERN.findall(query)

    temporal_references = DATE_PATTERN.findall(query)
    lower_query = query.lower()
    temporal_references.extend(kw for kw in TEMPORAL_KEYWORDS if kw in lower_query)

    return ObjectIntelligence(
        entities=_ordered_unique(entities),
        identifiers=_ordered_unique(identifiers),
        temporal_references=_ordered_unique(temporal_references),
        relationships=[],
    )
