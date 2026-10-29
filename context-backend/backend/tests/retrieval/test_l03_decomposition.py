from app.retrieval.intelligence.decomposition import decompose_query


def test_fixed_phrase_pros_and_cons_not_split():
    assert not decompose_query("pros and cons of microservices", "R1").is_decomposed


def test_fixed_phrase_terms_and_conditions_not_split():
    assert not decompose_query("summarise the terms and conditions", "R1").is_decomposed


def test_two_real_questions_are_split():
    res = decompose_query(
        "what is the refund policy and how do I contact support", "R1"
    )
    assert res.is_decomposed
    assert [s.query for s in res.subqueries] == [
        "what is the refund policy",
        "how do I contact support",
    ]


def test_max_subqueries_respected():
    res = decompose_query(
        "what is plan A pricing and what is plan B pricing and what is plan C pricing",
        "R1",
        max_subqueries=2,
    )
    assert len(res.subqueries) == 2


def test_max_subqueries_one_disables_decomposition():
    res = decompose_query(
        "what is the refund policy and how do I contact support", "R1", max_subqueries=1
    )
    assert not res.is_decomposed


def test_empty_query():
    assert not decompose_query("", "R1").is_decomposed


def test_parts_over_limit_are_folded_not_dropped():
    res = decompose_query(
        "what is plan A pricing and what is plan B pricing and what is plan C pricing",
        "R1",
        max_subqueries=2,
    )
    assert [s.query for s in res.subqueries] == [
        "what is plan A pricing",
        "what is plan B pricing and what is plan C pricing",
    ]
