"""
Unit tests for L01 (Unified Retrieval Contract).

No database, no network. Run from the backend folder:

    python -m pytest tests/retrieval/test_l01_contract.py -v
"""
import pytest

from app.core.enums import ExecutionProfile, RequestSourceType
from app.retrieval.canonical.builder import build_canonical_request
from app.retrieval.canonical.exceptions import CanonicalizationError
from app.retrieval.intake.normalize import normalize_request
from app.retrieval.schemas import ActorModel, LifecycleContext, RetrievalRequestCreate
from app.retrieval.security.constraints import ConstraintError, validate_constraints

ACTOR = ActorModel(actor_type="USER", actor_id="USR1")


def contract(**kw):
    kw.setdefault("instruction", "What is ContextAPI?")
    kw.setdefault("actor", ACTOR)
    kw.setdefault("execution_context", {"scope": {"project_id": "PROJ1"}})
    return build_canonical_request(normalize_request(RetrievalRequestCreate(**kw)))


def with_context(**extra):
    ctx = {"scope": {"project_id": "PROJ1"}}
    ctx.update(extra)
    return contract(execution_context=ctx)


# ------------------------------------------------------------ identity etc.
def test_contract_carries_identity_source_scope_and_query():
    c = contract(source_type=RequestSourceType.AGENT)
    assert c.request_id.startswith("req_")
    assert c.source_type == RequestSourceType.AGENT
    assert c.actor.actor_id == "USR1"
    assert c.scope == {"project_id": "PROJ1"}
    assert c.query == "What is ContextAPI?"


def test_lifecycle_and_source_metadata_are_carried():
    c = contract(
        lifecycle=LifecycleContext(request_id="r1", correlation_id="trace-1", idempotency_key="k1"),
        source_metadata={"agent_id": "planner-7"},
    )
    assert c.lifecycle.correlation_id == "trace-1"
    assert c.lifecycle.idempotency_key == "k1"
    assert c.request_metadata == {"agent_id": "planner-7", "client_request_id": "r1"}


def test_contract_is_immutable():
    c = contract()
    with pytest.raises(Exception):
        c.query = "changed"


def test_scope_must_be_an_object():
    with pytest.raises(CanonicalizationError) as exc:
        contract(execution_context={"scope": "PROJ1"})
    assert exc.value.field == "scope"


# ----------------------------------------------------------------- profile
def test_profile_defaults_to_standard():
    c = contract()
    assert c.profile == ExecutionProfile.STANDARD
    assert c.execution_metadata["profile"] == "STANDARD"


@pytest.mark.parametrize("raw,expected", [
    ("FAST", ExecutionProfile.FAST),
    ("deep", ExecutionProfile.DEEP),
    ("Collaborative", ExecutionProfile.COLLABORATIVE),
])
def test_profile_is_parsed_case_insensitively(raw, expected):
    assert with_context(profile=raw).profile == expected


def test_unknown_profile_is_rejected():
    with pytest.raises(CanonicalizationError) as exc:
        with_context(profile="TURBO")
    assert exc.value.error_code == "INVALID_PROFILE"


# ------------------------------------------------------------- constraints
def test_no_constraints_gives_empty_dict():
    assert contract().constraints == {}


def test_valid_constraints_are_kept_and_deduplicated():
    c = with_context(constraints={
        "document_ids": ["DOC1", "DOC2", "DOC1"],
        "mime_types": ["application/pdf"],
        "created_after": "2026-01-01",
    })
    assert c.constraints["document_ids"] == ["DOC1", "DOC2"]
    assert c.constraints["mime_types"] == ["application/pdf"]
    assert c.constraints["created_after"] == "2026-01-01"


def test_unsupported_constraint_is_rejected_not_ignored():
    with pytest.raises(CanonicalizationError) as exc:
        with_context(constraints={"author": "me"})
    assert exc.value.error_code == "UNSUPPORTED_CONSTRAINT"
    assert exc.value.field == "constraints.author"


def test_constraint_with_wrong_type_is_rejected():
    with pytest.raises(CanonicalizationError):
        with_context(constraints={"document_ids": "DOC1"})
    with pytest.raises(CanonicalizationError):
        with_context(constraints={"document_ids": [1, 2]})


def test_constraint_with_bad_date_is_rejected():
    with pytest.raises(CanonicalizationError):
        with_context(constraints={"created_after": "not-a-date"})


def test_constraint_list_size_is_limited():
    with pytest.raises(ConstraintError):
        validate_constraints({"document_ids": [f"D{i}" for i in range(101)]})


def test_validate_constraints_handles_none_and_empty():
    assert validate_constraints(None) == {}
    assert validate_constraints({}) == {}