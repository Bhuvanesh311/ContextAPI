from typing import Dict, List, Optional
import time

from app.retrieval.planning.schemas import RetrievalPlan
from app.retrieval.engine.schemas import (
    CandidateEvidenceSet,
    CandidateEvidence,
    ExecutionTrace,
    RawRetrievalResult,
    utc_now,
)
from app.retrieval.engine.enums import ExecutionStatus, OperatorType
from app.retrieval.engine.operators.base import BaseOperator
from app.retrieval.engine.exceptions import ExecutionTimeoutError, ScopeViolationError

_CAPABILITY_OPERATOR_TYPES = {
    "cap_semantic": OperatorType.SEMANTIC,
    "cap_lexical": OperatorType.LEXICAL,
    "cap_hybrid": OperatorType.HYBRID,
    "cap_structured": OperatorType.STRUCTURED,
}


def _operator_type_for(capability_id: str) -> OperatorType:
    """Trace label for a capability (was hard-coded to SEMANTIC for every step)."""
    return _CAPABILITY_OPERATOR_TYPES.get(capability_id, OperatorType.SEMANTIC)


class EngineExecutor:
    def __init__(self, operators: List[BaseOperator], resolver=None):
        self._operators = {op.capability_id: op for op in operators}
        self.resolver = resolver
        
    def execute_plan(self, plan: RetrievalPlan, context_data: Optional[Dict] = None) -> CandidateEvidenceSet:
        # NOTE (fix): context_data is now forwarded to operators, so a
        # request's top_k actually reaches SemanticOperator/etc. Before this
        # change it was always called with {} and operators fell back to a
        # hardcoded default of 10.
        context_data = context_data or {}

        start_time_global = time.time()
        max_latency = plan.execution_limits.max_latency_ms / 1000.0
        max_steps = plan.execution_limits.max_steps
        
        traces = []
        all_raw_results = []
        
        completed_steps = set()
        failed_steps = set()
        
        status = ExecutionStatus.SUCCESS
        fatal_error = None
        
        pending_steps = list(plan.graph.steps)
        executed_step_ids = set()
        
        while pending_steps:
            if time.time() - start_time_global > max_latency:
                status = ExecutionStatus.FAILED
                fatal_error = "ExecutionTimeoutError: Plan exceeded max latency."
                break
                
            if len(executed_step_ids) >= max_steps:
                break # We reached the maximum allowed steps

            progress_made = False
            
            for step in list(pending_steps):
                # Check dependencies
                deps_satisfied = True
                deps_failed = False
                for dep in step.depends_on:
                    if dep in failed_steps:
                        deps_failed = True
                        break
                    if dep not in completed_steps:
                        deps_satisfied = False
                        break
                        
                if deps_failed:
                    pending_steps.remove(step)
                    failed_steps.add(step.step_id)
                    progress_made = True
                    continue
                    
                if not deps_satisfied:
                    continue
                    
                pending_steps.remove(step)
                progress_made = True
                
                if time.time() - start_time_global > max_latency:
                    status = ExecutionStatus.FAILED
                    fatal_error = "ExecutionTimeoutError: Plan exceeded max latency."
                    break
                    
                if len(executed_step_ids) >= max_steps:
                    status = ExecutionStatus.FAILED
                    fatal_error = "ExecutionLimitsError: Plan exceeded max steps."
                    break

                # Check if duplicate step id
                if step.step_id in executed_step_ids:
                    status = ExecutionStatus.FAILED
                    fatal_error = f"Duplicate step execution for {step.step_id}"
                    break
                    
                executed_step_ids.add(step.step_id)
                
                step_start = utc_now()
                step_start_time = time.time()
                
                # We extract the execution logic into a retry block
                success = False
                attempt_capabilities = [step.capability_id]
                
                if plan.fallback_policy and plan.fallback_policy.fallback_capabilities:
                    attempt_capabilities.extend(list(plan.fallback_policy.fallback_capabilities)[:plan.fallback_policy.max_attempts])
                
                for cap_idx, cap_id in enumerate(attempt_capabilities):
                    operator = self._operators.get(cap_id)
                    if not operator:
                        traces.append(ExecutionTrace(
                            step_id=step.step_id,
                            operator_type=_operator_type_for(cap_id),
                            status=ExecutionStatus.FAILED,
                            start_time=step_start,
                            end_time=utc_now(),
                            error_message=f"No operator found for capability: {cap_id}",
                            retry_count=cap_idx
                        ))
                        continue
                    
                    try:
                        raw_results = operator.execute(step, context_data=context_data)
                        all_raw_results.extend(raw_results)
                        
                        traces.append(ExecutionTrace(
                            step_id=step.step_id,
                            operator_type=_operator_type_for(cap_id),
                            status=ExecutionStatus.SUCCESS,
                            start_time=step_start,
                            end_time=utc_now(),
                            latency_ms=int((time.time() - step_start_time) * 1000),
                            candidates_found=len(raw_results),
                            retry_count=cap_idx
                        ))
                        completed_steps.add(step.step_id)
                        success = True
                        break
                    except ScopeViolationError:
                        # Never retry an unscoped search with another capability.
                        raise
                    except Exception as e:
                        traces.append(ExecutionTrace(
                            step_id=step.step_id,
                            operator_type=_operator_type_for(cap_id),
                            status=ExecutionStatus.FAILED,
                            start_time=step_start,
                            end_time=utc_now(),
                            latency_ms=int((time.time() - step_start_time) * 1000),
                            error_message=str(e),
                            retry_count=cap_idx
                        ))
                        
                if not success:
                    failed_steps.add(step.step_id)
                    status = ExecutionStatus.PARTIAL
                    
            if not progress_made and pending_steps:
                status = ExecutionStatus.FAILED
                fatal_error = "Deadlock or unresolved dependency in execution graph."
                break

        resolved_candidates = []
        if self.resolver and all_raw_results:
            resolved_candidates = self.resolver.resolve(all_raw_results)

        return CandidateEvidenceSet(
            plan_id=plan.plan_id,
            status=status,
            candidates=tuple(resolved_candidates),
            traces=tuple(traces),
            total_latency_ms=int((time.time() - start_time_global) * 1000),
            fatal_error=fatal_error
        )