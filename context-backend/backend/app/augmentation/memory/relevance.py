"""
L8 relevance and priority scoring — deterministic, no LLM.

score_relevance()      → 0..1 term-coverage of query against content
compute_priority_score() → combined score: relevance + source-type priority + recency
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.retrieval.textutil import term_coverage

if TYPE_CHECKING:
    from app.augmentation.memory.schemas import MemorySourceType


# Weight of each dimension in the combined priority score
_RELEVANCE_WEIGHT = 0.5
_SOURCE_WEIGHT    = 0.3
_RECENCY_WEIGHT   = 0.2

# Source-type authority: how trustworthy / actionable each source is
_SOURCE_PRIORITY: dict = {}   # populated lazily to avoid import-time circular issues


def _source_priority(source_type) -> float:
    global _SOURCE_PRIORITY
    if not _SOURCE_PRIORITY:
        from app.augmentation.memory.schemas import MemorySourceType as MST
        _SOURCE_PRIORITY = {
            MST.AGENT:     1.0,   # explicit agent-set state
            MST.EVIDENCE:  0.9,   # prior retrieval results
            MST.LONG_TERM: 0.7,   # established user knowledge
            MST.SESSION:   0.5,   # conversational context
        }
    return _SOURCE_PRIORITY.get(source_type, 0.5)


def _recency(ts_str: str) -> float:
    """Linear decay: 1.0 = just now, 0.0 = 24 h ago."""
    if not ts_str:
        return 0.5
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return max(0.0, 1.0 - age_hours / 24.0)
    except (ValueError, TypeError, OverflowError):
        return 0.5


def score_relevance(query: str, content: str) -> float:
    """0..1: share of query topic terms covered by content."""
    if not query or not content:
        return 0.0
    ratio, _, _ = term_coverage(query, content)
    return round(ratio, 3)


def compute_priority_score(relevance: float, source_type, ts_str: str = "") -> float:
    """Combined ranking score (0..1)."""
    prio = _source_priority(source_type)
    rec  = _recency(ts_str)
    return round(
        relevance * _RELEVANCE_WEIGHT
        + prio     * _SOURCE_WEIGHT
        + rec      * _RECENCY_WEIGHT,
        3,
    )
