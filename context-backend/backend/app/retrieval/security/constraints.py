"""
Caller constraints (L01 validates the shape, L02 applies them).

Supported keys (anything else is rejected by L01 instead of being ignored,
because a silently ignored constraint would widen the search):

    document_ids   list[str]   only these documents
    mime_types     list[str]   only documents with one of these MIME types
    created_after  ISO date    documents created on/after
    created_before ISO date    documents created before
"""

from datetime import datetime
from typing import Any, Dict, List, Tuple

ALLOWED_CONSTRAINT_KEYS = frozenset({"document_ids", "mime_types", "created_after", "created_before"})
MAX_LIST_ITEMS = 100


class ConstraintError(ValueError):
    def __init__(self, message: str, key: str):
        super().__init__(message)
        self.key = key


def _parse_date(key: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise ConstraintError(f"'{key}' must be an ISO date string", key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConstraintError(f"'{key}' is not a valid ISO date", key) from exc
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def validate_constraints(constraints: Dict[str, Any]) -> Dict[str, Any]:
    """Return a cleaned copy or raise ConstraintError."""
    if constraints is None:
        return {}
    if not isinstance(constraints, dict):
        raise ConstraintError("constraints must be an object", "constraints")

    cleaned: Dict[str, Any] = {}
    for key, value in constraints.items():
        if key not in ALLOWED_CONSTRAINT_KEYS:
            raise ConstraintError(f"Unsupported constraint '{key}'", key)
        if key in ("document_ids", "mime_types"):
            if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
                raise ConstraintError(f"'{key}' must be a list of non-empty strings", key)
            if len(value) > MAX_LIST_ITEMS:
                raise ConstraintError(f"'{key}' has more than {MAX_LIST_ITEMS} items", key)
            cleaned[key] = list(dict.fromkeys(value))
        else:
            _parse_date(key, value)
            cleaned[key] = value
    return cleaned


def parsed_dates(constraints: Dict[str, Any]) -> Tuple[Any, Any]:
    after = _parse_date("created_after", constraints["created_after"]) if "created_after" in constraints else None
    before = _parse_date("created_before", constraints["created_before"]) if "created_before" in constraints else None
    return after, before