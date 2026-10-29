
from typing import Dict, Any, List, Set
from app.retrieval.planning.schemas import RetrievalPlan, ExecutionGraph
from app.retrieval.planning.exceptions import (
    SecurityBoundaryViolationError,
    GraphInvalidError,
    LimitExceededError,
    PlanValidationFailedError,
    QueryBindingFailureError,
)

def is_subset_scope(step_scope: Dict[str, Any], effective_scope: Dict[str, Any]) -> bool:
    """
    Validates if step_scope is a strict subset of effective_scope.
    This is a critical L04 boundary rule.
    If effective_scope requires a filter (e.g. tenant_id), step_scope MUST include it
    or be more restrictive. Omitting it would fail open (broaden scope).
    """
    for key, allowed_values in effective_scope.items():
        if key not in step_scope:
            return False  # Omission broadens scope!
        
        step_values = step_scope[key]
        if isinstance(step_values, list) and isinstance(allowed_values, list):
            if not set(step_values).issubset(set(allowed_values)):
                return False
        elif step_values != allowed_values:
            return False
            
    # Check if step tries to request keys not in effective scope at all
    for key in step_scope:
        if key not in effective_scope:
            return False
            
    return True

def validate_acyclic_graph(graph: ExecutionGraph) -> None:
    """
    Validates that the execution graph contains no cycles using DFS.
    """
    adj = {step.step_id: step.depends_on for step in graph.steps}
    visited = set()
    rec_stack = set()
    
    def dfs(node_id: str) -> bool:
        visited.add(node_id)
        rec_stack.add(node_id)
        
        for neighbor in adj.get(node_id, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.remove(node_id)
        return False
        
    for step in graph.steps:
        if step.step_id not in visited:
            if dfs(step.step_id):
                raise GraphInvalidError(f"Execution graph contains a cycle starting near step {step.step_id}")

def validate_plan(plan: RetrievalPlan) -> RetrievalPlan:
    """
    Performs full architectural validation of the RetrievalPlan before freeze.
    """
    if not plan.graph.steps:
        raise PlanValidationFailedError("Plan must contain at least one step unless cancelled.")
        
    if len(plan.graph.steps) > plan.execution_limits.max_steps:
        raise LimitExceededError(f"Plan exceeds max steps ({len(plan.graph.steps)} > {plan.execution_limits.max_steps})")
        
    for step in plan.graph.steps:
        if not step.query_binding.query_text.strip():
            raise QueryBindingFailureError(
                f"Step {step.step_id} has an empty query_text — cannot execute."
            )
        if not is_subset_scope(step.step_scope, plan.effective_scope):
            raise SecurityBoundaryViolationError(
                f"Step {step.step_id} attempts to expand scope beyond L02 effective_scope."
            )
            
    validate_acyclic_graph(plan.graph)
    
    return plan