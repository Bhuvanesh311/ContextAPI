
from typing import List, Dict, Any
import uuid

from app.core.enums import RetrievalRequirementType
from app.retrieval.intelligence.schemas import QueryAnalysisResult
from app.retrieval.planning.schemas import (
    RetrievalStep,
    QueryBinding,
    ExecutionGraph,
    ExecutionLimits,
)
from app.retrieval.planning.exceptions import StrategyInvalidError, CapabilityUnavailableError
from app.retrieval.planning.capabilities import registry


class StrategyEngine:
    """
    Translates L03 Intelligence requirements into L04 Retrieval Steps.
    Implements minimal-plan principle.
    """

    @classmethod
    def create_minimal_graph(
        cls,
        l03_result: QueryAnalysisResult,
        limits: ExecutionLimits | None = None,
    ) -> ExecutionGraph:
        limits = limits or ExecutionLimits()
        steps: List[RetrievalStep] = []
        effective_scope = l03_result.request.effective_scope

        # Read requirements into a local list — never mutate the frozen L03 model.
        requirements: List[RetrievalRequirementType] = (list(
            l03_result.query_intelligence.retrieval_requirements
        ) or [RetrievalRequirementType.LEXICAL])[: limits.max_steps]

        # 1. Decomposed query: one step per (requirement × subquery) pair.
        # To fit the profile's step budget, extra subqueries are folded into the
        # last one (nothing is dropped, and the validator never rejects the plan).
        texts = [sq.query for sq in l03_result.decomposition.subqueries]
        allowed = max(1, min(limits.max_subqueries, limits.max_steps // len(requirements)))
        if len(texts) > allowed:
            texts = texts[: allowed - 1] + [" and ".join(texts[allowed - 1:])]
        if l03_result.decomposition.is_decomposed and len(texts) > 1:
            for req_type in requirements:
                caps = registry.get_eligible_capabilities(req_type)
                if not caps:
                    raise CapabilityUnavailableError(
                        f"No available capability for {req_type}"
                    )
                selected_cap = caps[0]  # minimal-plan: first eligible

                for text in texts:
                    steps.append(RetrievalStep(
                        step_id=str(uuid.uuid4()),
                        capability_id=selected_cap.capability_id,
                        query_binding=QueryBinding(
                            binding_type="subquery",
                            query_text=text,
                            subquery_id=str(uuid.uuid4()),  # unique per step, not parent id
                        ),
                        step_scope=effective_scope,
                        depends_on=(),
                    ))
            return ExecutionGraph(steps=tuple(steps))

        # 2. Non-decomposed: one step per requirement (all parallel)
        query_text = l03_result.normalized_query or l03_result.original_query or ""

        for req_type in requirements:
            caps = registry.get_eligible_capabilities(req_type)
            if not caps:
                raise CapabilityUnavailableError(
                    f"No available capability for {req_type}"
                )
            selected_cap = caps[0]
            steps.append(RetrievalStep(
                step_id=str(uuid.uuid4()),
                capability_id=selected_cap.capability_id,
                query_binding=QueryBinding(
                    binding_type="normalized" if l03_result.normalized_query else "original",
                    query_text=query_text,
                ),
                step_scope=effective_scope,
                depends_on=(),
            ))

        return ExecutionGraph(steps=tuple(steps))
