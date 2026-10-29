"""
Unit tests for L00 (Request Intake & Source Adaptation).

No database, no network. Run from the backend folder:

    python -m pytest tests/retrieval/test_l00_intake.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.enums import RequestSourceType
from app.retrieval.intake.normalize import normalize_request
from app.retrieval.intake.validation import IntakeValidationError, validate_intake_request
from app.retrieval.schemas import ActorModel, LifecycleContext, RetrievalRequestCreate


ACTOR = ActorModel(actor_type="USER", actor_id="USR1")
NOW = datetime.now(timezone.utc).replace(tzinfo=None)


def make(**kw):
    kw.setdefault("instruction", "What is ContextAPI?")
    kw.setdefault("actor", ACTOR)
    return RetrievalRequestCreate(**kw)


# ---------------------------------------------------------- validation
def test_valid_request_passes():
    validate_intake_request(make())


def test_empty_instruction_is_rejected():
    with pytest.raises(IntakeValidationError) as exc:
        validate_intake_request(make(instruction="  \n\t "))
    assert exc.value.error_code == "INVALID_REQUEST"


def test_control_characters_only_is_rejected():
    with pytest.raises(IntakeValidationError):
        validate_intake_request(make(instruction="\x00\x01\x02"))


def test_too_long_instruction_is_rejected():
    with pytest.raises(IntakeValidationError) as exc:
        validate_intake_request(make(instruction="a" * 10_001))
    assert exc.value.error_code == "REQUEST_TOO_LARGE"


@pytest.mark.parametrize("source", [
    RequestSourceType.USER, RequestSourceType.AGENT,
    RequestSourceType.PLANNER_AGENT, RequestSourceType.WORKFLOW,
])
def test_client_sources_are_accepted(source):
    validate_intake_request(make(source_type=source))


def test_client_cannot_claim_internal_source():
    with pytest.raises(IntakeValidationError) as exc:
        validate_intake_request(make(source_type=RequestSourceType.INTERNAL))
    assert exc.value.error_code == "SOURCE_NOT_ALLOWED"


def test_deadline_in_the_past_is_rejected():
    life = LifecycleContext(request_id="r1", deadline=NOW - timedelta(minutes=1))
    with pytest.raises(IntakeValidationError) as exc:
        validate_intake_request(make(lifecycle=life))
    assert exc.value.error_code == "DEADLINE_EXCEEDED"


def test_future_deadline_is_accepted():
    life = LifecycleContext(request_id="r1", deadline=NOW + timedelta(minutes=5))
    validate_intake_request(make(lifecycle=life))


def test_oversized_correlation_id_is_rejected():
    life = LifecycleContext(request_id="r1", correlation_id="x" * 200)
    with pytest.raises(IntakeValidationError) as exc:
        validate_intake_request(make(lifecycle=life))
    assert exc.value.error_code == "INVALID_LIFECYCLE"


# -------------------------------------------------------- normalization
def test_instruction_is_cleaned():
    n = normalize_request(make(instruction="  What\x00   is \n\n ContextAPI?  "))
    assert n.retrieval_instruction == "What is ContextAPI?"


def test_request_id_is_generated_when_missing():
    n = normalize_request(make())
    assert n.request_id.startswith("req_")
    assert n.lifecycle.request_id == n.request_id


def test_caller_request_id_is_not_the_identity_but_kept_for_tracing():
    n = normalize_request(make(lifecycle=LifecycleContext(request_id="my-req-1")))
    assert n.request_id.startswith("req_") and n.request_id != "my-req-1"
    assert n.lifecycle.request_id == n.request_id
    assert n.lifecycle.correlation_id == "my-req-1"
    assert n.source_metadata["client_request_id"] == "my-req-1"


def test_given_correlation_id_is_not_overwritten():
    n = normalize_request(make(lifecycle=LifecycleContext(request_id="r1", correlation_id="trace-9")))
    assert n.lifecycle.correlation_id == "trace-9"


def test_source_and_actor_are_carried_through():
    n = normalize_request(make(source_type=RequestSourceType.AGENT))
    assert n.source_type == RequestSourceType.AGENT
    assert n.actor.actor_id == "USR1"


def test_source_metadata_keeps_only_short_scalars():
    n = normalize_request(make(source_metadata={
        "agent_id": "planner-7", "attempt": 2, "nested": {"x": 1}, "long": "y" * 500,
    }))
    assert n.source_metadata["agent_id"] == "planner-7"
    assert n.source_metadata["attempt"] == 2
    assert "nested" not in n.source_metadata
    assert len(n.source_metadata["long"]) == 200


def test_context_is_extracted_unchanged():
    n = normalize_request(make(
        resource_context={"kind": "pdf"},
        execution_context={"scope": {"project_id": "PROJ1"}},
    ))
    assert n.resource_context == {"kind": "pdf"}
    assert n.execution_context == {"scope": {"project_id": "PROJ1"}}