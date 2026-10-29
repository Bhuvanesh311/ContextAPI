"""
Unit tests for L03 (Query Intelligence).

Run from the backend folder:
    python -m pytest tests/retrieval/test_l03_intelligence.py -v
"""
import pytest

from app.core.enums import QueryIntent, QueryComplexity, RetrievalRequirementType
from app.retrieval.intelligence.query import analyze_query_intelligence
from app.retrieval.intelligence.schemas import QueryIntelligence


def test_empty_query_intelligence():
    res = analyze_query_intelligence("")
    assert isinstance(res, QueryIntelligence)
    assert res.intent == QueryIntent.UNKNOWN
    assert res.complexity == QueryComplexity.LOW
    assert res.ambiguity_score == 1.0
    assert res.retrieval_requirements == []


def test_fact_lookup_intent():
    res = analyze_query_intelligence("What is the revenue for Q3?")
    assert res.intent == QueryIntent.FACT_LOOKUP
    assert RetrievalRequirementType.SEMANTIC in res.retrieval_requirements


def test_comparison_intent_and_complexity():
    res = analyze_query_intelligence("Compare the performance of model A and model B")
    assert res.intent == QueryIntent.COMPARISON
    # ' and ' triggers HIGH complexity
    assert res.complexity == QueryComplexity.HIGH
    assert RetrievalRequirementType.RELATIONAL in res.retrieval_requirements


def test_explanation_intent():
    res = analyze_query_intelligence("Explain how vector retrieval works")
    assert res.intent == QueryIntent.EXPLANATION


def test_exact_retrieval_requirement():
    res = analyze_query_intelligence('Find the exact match for "error 404"')
    assert RetrievalRequirementType.EXACT in res.retrieval_requirements


def test_short_query_ambiguity():
    res = analyze_query_intelligence("hi")
    assert res.ambiguity_score >= 0.8