
import uuid
from typing import Optional

from app.retrieval.intelligence.schemas import QueryAnalysisResult
from app.retrieval.planning.schemas import (
    RetrievalPlan, 
    ExecutionLimits, 
    StopConditions, 
    FallbackPolicy
)
from app.retrieval.planning.strategies import StrategyEngine
from app.retrieval.planning.validator import validate_plan
from app.retrieval.planning.exceptions import InputInvalidError

class L04Planner:
    """
    Core orchestrator for L04 Retrieval Planning & Strategy.
    Constructs, validates, and freezes the plan.
    """
    
    def __init__(self, execution_limits: Optional[ExecutionLimits] = None):
        self.execution_limits = execution_limits or ExecutionLimits()
        
    def plan(self, l03_result: QueryAnalysisResult) -> RetrievalPlan:
        if not isinstance(l03_result, QueryAnalysisResult):
            raise InputInvalidError("Input must be a valid QueryAnalysisResult")
            
        request_id = l03_result.request.request.request_id
        effective_scope = l03_result.request.effective_scope

        lifecycle = l03_result.request.request.lifecycle
        correlation_id = (
            lifecycle.correlation_id
            if lifecycle and lifecycle.correlation_id
            else request_id
        )
        
        # 1. Select Strategy & Construct Graph
        graph = StrategyEngine.create_minimal_graph(l03_result, self.execution_limits)
        
        # 2. Define Stop Conditions & Fallback
        stop_conditions = StopConditions(
            sufficient_evidence=True,
            max_rounds_reached=True,
            deadline_exceeded=True,
            budget_exhausted=True
        )

        # Build fallback capability list: capabilities not used as primary in
        # any step, ordered from most capable (hybrid) to least (lexical).
        # This means if cap_hybrid fails, the executor retries with cap_semantic.
        primary_cap_ids = {step.capability_id for step in graph.steps}
        _fallback_order = ("cap_hybrid", "cap_semantic", "cap_lexical")
        fallback_caps = tuple(c for c in _fallback_order if c not in primary_cap_ids)

        fallback_policy = FallbackPolicy(
            strategy_id="standard_degradation",
            max_attempts=len(fallback_caps),
            fallback_capabilities=fallback_caps,
        )
        
        # 3. Assemble Plan
        plan = RetrievalPlan(
            plan_id=str(uuid.uuid4()),
            request_id=request_id,
            correlation_id=correlation_id,
            effective_scope=effective_scope,
            planning_summary="Constructed via L04 minimal-plan deterministic heuristic.",
            graph=graph,
            execution_limits=self.execution_limits,
            stop_conditions=stop_conditions,
            fallback_policy=fallback_policy
        )
        
        # 4. Validate & Freeze Plan
        validated_plan = validate_plan(plan)
        
        return validated_plan
