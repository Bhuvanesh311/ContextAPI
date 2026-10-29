
import re

from app.retrieval.intelligence.schemas import DecompositionResult, Subquery

MAX_SUBQUERIES = 3
# Each part must stand on its own as a question; this keeps fixed phrases like
# "pros and cons of X" or "terms and conditions" from being split.
_MIN_PART_WORDS = 3

_SPLIT_RE = re.compile(r'\s*[,;]?\s*\b(?:and|also)\b\s*', flags=re.IGNORECASE)


def decompose_query(
    query: str,
    parent_request_id: str,
    max_subqueries: int = MAX_SUBQUERIES,
) -> DecompositionResult:
    if not query:
        return DecompositionResult()

    parts = [p.strip(" ,;") for p in _SPLIT_RE.split(query)]
    parts = [p for p in parts if p]

    if len(parts) < 2 or any(len(p.split()) < _MIN_PART_WORDS for p in parts):
        return DecompositionResult()

    # Parts beyond the limit are folded into the last subquery, not dropped.
    limit = max(1, max_subqueries)
    if len(parts) > limit:
        parts = parts[: limit - 1] + [" and ".join(parts[limit - 1:])]

    subqueries = [
        Subquery(
            parent_request_id=parent_request_id,
            query=part,
            purpose=f"Part {i+1} of decomposed query",
        )
        for i, part in enumerate(parts)
    ]
    if len(subqueries) < 2:
        return DecompositionResult()

    return DecompositionResult(is_decomposed=True, subqueries=subqueries)
