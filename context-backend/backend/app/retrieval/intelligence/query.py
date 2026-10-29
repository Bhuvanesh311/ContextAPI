
import re
from typing import List

from app.core.enums import QueryIntent, QueryComplexity, RetrievalRequirementType
from app.retrieval.intelligence.schemas import QueryIntelligence


def analyze_query_intelligence(query: str) -> QueryIntelligence:
    if not query:
        return QueryIntelligence(
            intent=QueryIntent.UNKNOWN,
            complexity=QueryComplexity.LOW,
            ambiguity_score=1.0,
            retrieval_requirements=[],
        )

    lower_query = query.lower()
    words = query.split()
    length = len(words)

    # --- Complexity ---
    question_count = query.count("?")
    has_and = " and " in lower_query
    has_or = " or " in lower_query
    # Count distinct clause-level connectors (not just boolean operators)
    clause_connectors = sum([
        " because " in lower_query,
        " therefore " in lower_query,
        " however " in lower_query,
        " although " in lower_query,
        " whereas " in lower_query,
        (has_and and length > 15),
        (has_or and length > 15),
    ])

    if length > 50 or question_count > 1 or (has_and and has_or and length > 20):
        complexity = QueryComplexity.VERY_HIGH
    elif length > 30 or clause_connectors >= 2:
        complexity = QueryComplexity.HIGH
    elif length > 10:
        complexity = QueryComplexity.MEDIUM
    else:
        complexity = QueryComplexity.LOW

    # --- Intent (ordered most-specific → least-specific) ---
    if any(kw in lower_query for kw in [
        "investigate", "root cause", "trace", "incident",
        "what happened", "why did", "track down", "debug", "troubleshoot",
    ]):
        intent = QueryIntent.INVESTIGATION

    elif any(kw in lower_query for kw in [
        "compare", "comparison", "difference", "differences", "versus",
        " vs ", "contrast", "distinguish", "similarity", "similarities",
    ]):
        intent = QueryIntent.COMPARISON

    elif any(kw in lower_query for kw in [
        "related to", "connection between", "linked to", "relationship between",
        "how does", "interact with", "associated with", "depends on",
        "dependency", "dependencies",
    ]):
        intent = QueryIntent.RELATIONSHIP

    elif any(kw in lower_query for kw in [
        "step by step", "workflow", "process", "procedure",
        "and then", "first then", "following steps", "sequence of",
    ]) or (complexity == QueryComplexity.VERY_HIGH and question_count > 1):
        intent = QueryIntent.MULTI_STEP

    elif any(kw in lower_query for kw in [
        "analyze", "analysis", "evaluate", "assess", "assessment",
        "audit", "examine", "review", "insights", "summarize", "summary",
    ]):
        intent = QueryIntent.ANALYSIS

    elif any(kw in lower_query for kw in [
        "how to", "explain", "describe",
        "definition of", "meaning of", "overview of",
    ]):
        intent = QueryIntent.EXPLANATION

    elif any(kw in lower_query for kw in [
        "list all", "show all", "find all", "search for", "filter",
        "all documents", "all files", "display all", "get all",
    ]):
        intent = QueryIntent.METADATA_SEARCH

    elif re.search(r'"[^"]+"', query) or any(kw in lower_query for kw in [
        "exact", "exactly", "find by id", "document id", "record id",
    ]):
        intent = QueryIntent.EXACT_LOOKUP

    elif re.search(r"\b(who|what|where|when|find)\b", lower_query):
        intent = QueryIntent.FACT_LOOKUP

    else:
        intent = QueryIntent.UNKNOWN

    # Comparing two named things with "and" is inherently multi-entity work.
    if intent == QueryIntent.COMPARISON and has_and and complexity == QueryComplexity.LOW:
        complexity = QueryComplexity.HIGH

    # --- Retrieval requirements ---
    requirements: List[RetrievalRequirementType] = [RetrievalRequirementType.SEMANTIC]
    if re.search(r'"[^"]+"', query) or "exact" in lower_query:
        requirements.append(RetrievalRequirementType.EXACT)
    if complexity in (QueryComplexity.HIGH, QueryComplexity.VERY_HIGH) or intent in (
        QueryIntent.RELATIONSHIP, QueryIntent.INVESTIGATION, QueryIntent.MULTI_STEP
    ):
        requirements.append(RetrievalRequirementType.RELATIONAL)

    # --- Ambiguity ---
    ambiguity = 0.0
    if length < 3:
        ambiguity = 0.8
    elif intent == QueryIntent.UNKNOWN:
        ambiguity = 0.5
    elif complexity == QueryComplexity.VERY_HIGH and intent == QueryIntent.UNKNOWN:
        ambiguity = 0.7

    return QueryIntelligence(
        intent=intent,
        complexity=complexity,
        ambiguity_score=ambiguity,
        retrieval_requirements=list(dict.fromkeys(requirements)),  # dedup, order-stable
    )
