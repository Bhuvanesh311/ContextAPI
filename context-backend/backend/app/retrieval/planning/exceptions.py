
class L04PlanningError(Exception):
    """Base exception for all L04 Planning failures."""
    pass

class InputInvalidError(L04PlanningError):
    """Raised when L02 or L03 inputs are missing or malformed."""
    pass

class SecurityBoundaryViolationError(L04PlanningError):
    """CRITICAL: Raised when planning attempts to expand L02 effective scope."""
    pass

class CapabilityUnavailableError(L04PlanningError):
    """Raised when a required capability is missing or not available."""
    pass

class CapabilityIneligibleError(L04PlanningError):
    """Raised when a required capability exists but is ineligible for the context."""
    pass

class StrategyInvalidError(L04PlanningError):
    """Raised when the selected strategy is incompatible or unsupported."""
    pass

class QueryBindingFailureError(L04PlanningError):
    """Raised when a retrieval step has an invalid or missing query binding."""
    pass

class GraphInvalidError(L04PlanningError):
    """Raised when the execution graph is invalid (e.g., contains cycles or missing nodes)."""
    pass

class LimitExceededError(L04PlanningError):
    """Raised when the plan exceeds configured execution limits."""
    pass

class FallbackInvalidError(L04PlanningError):
    """Raised when the fallback policy is implicit, unbounded, or invalid."""
    pass

class StopConditionInvalidError(L04PlanningError):
    """Raised when stop conditions are unbounded or missing."""
    pass

class PlanValidationFailedError(L04PlanningError):
    """Raised when the final canonical plan fails structure or logic validation."""
    pass

class DependencyFailureError(L04PlanningError):
    """Raised when an external capability metadata or registry dependency fails."""
    pass

class DeadlineExceededError(L04PlanningError):
    """Raised when the planning deadline is exhausted."""
    pass

class CancellationError(L04PlanningError):
    """Raised when the planning process is cancelled."""
    pass

class InternalPlanningError(L04PlanningError):
    """CRITICAL: Raised on unexpected internal planning faults."""
    pass
