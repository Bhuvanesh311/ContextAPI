
import time
import logging
from typing import Any, Dict

from app.core.config import settings
from app.core.enums import AnalysisMethod, QueryIntent, QueryComplexity, RetrievalRequirementType
from app.retrieval.security.schemas import ScopedRetrievalContract
from app.retrieval.intelligence.schemas import QueryAnalysisResult, QueryIntelligence

from app.retrieval.intelligence.safety import analyze_safety
from app.retrieval.intelligence.object import analyze_objects
from app.retrieval.intelligence.query import analyze_query_intelligence
from app.retrieval.intelligence.memory import analyze_memory
from app.retrieval.intelligence.decomposition import decompose_query
from app.retrieval.intelligence.providers.router import ModelProviderRouter

logger = logging.getLogger(__name__)

# Lazy singleton — only instantiated when a profile with allow_llm=True is actually used
_provider_router: ModelProviderRouter | None = None


def _get_router() -> ModelProviderRouter:
    global _provider_router
    if _provider_router is None:
        _provider_router = ModelProviderRouter()
    return _provider_router


_LLM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [
                "EXACT_LOOKUP", "METADATA_SEARCH", "FACT_LOOKUP", "EXPLANATION",
                "COMPARISON", "ANALYSIS", "RELATIONSHIP", "INVESTIGATION", "MULTI_STEP", "UNKNOWN",
            ],
        },
        "complexity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]},
        "ambiguity_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "requires_relational": {"type": "boolean"},
    },
    "required": ["intent", "complexity", "ambiguity_score", "requires_relational"],
}


def _build_analysis_prompt(query: str, tier_a: QueryIntelligence) -> str:
    return (
        f"Analyze this retrieval query and classify it precisely.\n\n"
        f"Query: {query!r}\n\n"
        f"Initial deterministic classification:\n"
        f"  intent={tier_a.intent.value}, complexity={tier_a.complexity.value}, "
        f"ambiguity={tier_a.ambiguity_score:.2f}\n\n"
        f"Correct the classification if the initial one is wrong or UNKNOWN. "
        f"Set requires_relational=true if the query needs cross-document relationship traversal."
    )


def _apply_llm_refinement(base: QueryIntelligence, llm_raw: Dict[str, Any]) -> QueryIntelligence:
    try:
        intent_val = llm_raw.get("intent", base.intent.value)
        complexity_val = llm_raw.get("complexity", base.complexity.value)
        ambiguity_val = float(llm_raw.get("ambiguity_score", base.ambiguity_score))
        needs_relational = bool(llm_raw.get("requires_relational", False))

        try:
            intent = QueryIntent(intent_val)
        except ValueError:
            intent = base.intent

        try:
            complexity = QueryComplexity(complexity_val)
        except ValueError:
            complexity = base.complexity

        requirements = list(base.retrieval_requirements)
        if needs_relational and RetrievalRequirementType.RELATIONAL not in requirements:
            requirements.append(RetrievalRequirementType.RELATIONAL)

        return base.model_copy(update={
            "intent": intent,
            "complexity": complexity,
            "ambiguity_score": min(1.0, max(0.0, ambiguity_val)),
            "retrieval_requirements": requirements,
        })
    except Exception:
        return base


# Rough cost for a Tier C (external API) token.  Override via env if needed.
# At $2 / 1M tokens this is a conservative mid-market estimate.
_TIER_C_COST_PER_TOKEN: float = 2e-6


def _estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 characters per token (works for English prose)."""
    return max(1, len(text) // 4)


def analyze_request(
    contract: ScopedRetrievalContract,
    max_tokens: int | None = None,
    max_cost: float | None = None,
    time_budget_s: float | None = None,
) -> QueryAnalysisResult:
    """
    Layered Query Analyzer:
      Tier A — deterministic (always runs)
      Tier B — local SLM via Ollama (DEEP/COLLABORATIVE: allow_llm=True, low Tier A confidence)
      Tier C — external LLM fallback (COLLABORATIVE: max_llm_calls > 1)
    Fails open: any Tier B/C error falls back gracefully to the Tier A result.
    """
    raw_query = contract.request.query or ""

    # --- Tier A: Deterministic ---
    safety_assessment = analyze_safety(raw_query)
    object_intelligence = analyze_objects(raw_query)
    query_intelligence = analyze_query_intelligence(raw_query)
    memory_req = analyze_memory(raw_query)
    decomposition_res = decompose_query(
        raw_query,
        parent_request_id=contract.request.request_id,
        max_subqueries=getattr(contract.controls, "max_subqueries", 3),
    )

    analysis_method = AnalysisMethod.DETERMINISTIC
    tiers_executed = ["A"]
    llm_tokens_used = 0
    llm_cost_used = 0.0

    # --- Tier B/C: LLM refinement when profile allows and Tier A confidence is low ---
    controls = contract.controls
    needs_llm = (
        settings.QUERY_ANALYSIS_LLM_ENABLED
        and getattr(controls, "allow_llm", False)
        and (
            query_intelligence.intent == QueryIntent.UNKNOWN
            or query_intelligence.ambiguity_score >= 0.4
        )
    )

    if needs_llm:
        prompt = _build_analysis_prompt(raw_query, query_intelligence)
        prompt_tokens = _estimate_tokens(prompt)
        # Budget guard: if this LLM call alone would exhaust the caller's
        # token or cost budget, stay on Tier A so retrieval can still run.
        _est = prompt_tokens + 200  # conservative: prompt + response
        if max_tokens is not None and _est >= max_tokens:
            logger.debug(
                "Skipping Tier B/C: est. %d tokens >= budget %d; using Tier A",
                _est, max_tokens,
            )
            needs_llm = False
        elif max_cost is not None and _est * _TIER_C_COST_PER_TOKEN >= max_cost:
            logger.debug(
                "Skipping Tier B/C: est. cost %.6f >= budget %.6f; using Tier A",
                _est * _TIER_C_COST_PER_TOKEN, max_cost,
            )
            needs_llm = False

    if needs_llm:
        # prompt / prompt_tokens already set in the budget-check block above
        router = _get_router()
        # L03 may only spend its share of the request budget (Tier B + C
        # together), so L05-L07 always keep most of the time.
        if time_budget_s is None:
            time_budget_s = getattr(controls, "max_latency_ms", 60000) / 1000 * 0.2
        l3_deadline = time.monotonic() + time_budget_s
        llm_timeout = max(1, int(time_budget_s))

        # Tier B: local SLM (Ollama — no monetary cost, tokens still counted)
        try:
            raw = router.execute_tier_b(prompt, _LLM_SCHEMA, timeout=llm_timeout)
            response_tokens = _estimate_tokens(str(raw))
            llm_tokens_used += prompt_tokens + response_tokens
            query_intelligence = _apply_llm_refinement(query_intelligence, raw)
            analysis_method = AnalysisMethod.SEMANTIC_ROUTING
            tiers_executed.append("B")
        except Exception as exc:
            logger.debug("Tier B (Ollama) failed, staying on Tier A: %s", exc)

            # Tier C: external LLM — only for COLLABORATIVE (max_llm_calls > 1)
            remaining = l3_deadline - time.monotonic()
            if (
                getattr(controls, "max_llm_calls", 1) > 1
                and remaining >= 1
                and router.has_tier_c()
            ):
                try:
                    raw = router.execute_tier_c(
                        prompt, _LLM_SCHEMA, timeout=int(remaining), deadline=l3_deadline
                    )
                    response_tokens = _estimate_tokens(str(raw))
                    tier_c_tokens = prompt_tokens + response_tokens
                    llm_tokens_used += tier_c_tokens
                    llm_cost_used += tier_c_tokens * _TIER_C_COST_PER_TOKEN
                    query_intelligence = _apply_llm_refinement(query_intelligence, raw)
                    analysis_method = AnalysisMethod.LLM_AUGMENTED
                    tiers_executed.append("C")
                except Exception as exc2:
                    logger.debug("Tier C (external LLM) also failed, staying on Tier A: %s", exc2)

    # Confidence: Tier A UNKNOWN → 0.5; Tier A known → 0.8; LLM-refined → 0.9
    if analysis_method != AnalysisMethod.DETERMINISTIC:
        confidence = 0.9
    elif query_intelligence.intent == QueryIntent.UNKNOWN:
        confidence = 0.5
    else:
        confidence = 0.8

    return QueryAnalysisResult(
        request=contract,
        original_query=raw_query,
        normalized_query=raw_query.strip() if raw_query else None,
        resolved_objective=raw_query.strip() if raw_query else None,

        object_signals=object_intelligence,
        query_intelligence=query_intelligence,
        memory_requirement=memory_req,
        query_safety=safety_assessment,
        decomposition=decomposition_res,

        analysis_method=analysis_method,
        analysis_metadata={"tiers_executed": tiers_executed},
        confidence=confidence,
        llm_tokens_used=llm_tokens_used,
        llm_cost_used=llm_cost_used,
        analyzer_trace=["safety", "object", "query", "memory", "decomposition"],
    )
