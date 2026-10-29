from typing import Any, List, Mapping, Optional

from app.retrieval.engine.exceptions import ScopeViolationError


def require_version_scope(filters: Optional[Mapping[str, Any]]) -> List[str]:
    """
    Every L5 search must carry the L02 document_version_id "$in" scope.
    An empty or missing scope would mean "search every tenant's documents",
    so it is a hard error, never an unfiltered query.
    """
    scope = (filters or {}).get("document_version_id")
    if isinstance(scope, Mapping):
        ids = scope.get("$in")
    elif isinstance(scope, (list, tuple)):
        ids = scope
    else:
        ids = None
    if not ids:
        raise ScopeViolationError("Search without document scope is not allowed")
    return list(ids)
