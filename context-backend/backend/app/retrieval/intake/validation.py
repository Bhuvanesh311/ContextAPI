from datetime import datetime, timezone

from app.core.enums import RequestSourceType
from app.retrieval.schemas import RetrievalRequestCreate
from app.retrieval.textutil import clean_text

MAX_INSTRUCTION_LENGTH = 10_000
MAX_ID_LENGTH = 128
MAX_REQUEST_ID_LENGTH = 20  # matches retrieval_requests.request_id String(20)

# INTERNAL is trusted by L02, so a client must never be able to claim it.
CLIENT_ALLOWED_SOURCES = (
    RequestSourceType.USER,
    RequestSourceType.AGENT,
    RequestSourceType.PLANNER_AGENT,
    RequestSourceType.WORKFLOW,
)


class IntakeValidationError(Exception):
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code


def _now_like(value: datetime) -> datetime:
    now = datetime.now(timezone.utc)
    return now if value.tzinfo else now.replace(tzinfo=None)


def validate_intake_request(request: RetrievalRequestCreate) -> None:
    """Fail-fast structural validation (pydantic already checked the types)."""
    instruction = clean_text(request.instruction or "")
    if not instruction:
        raise IntakeValidationError("Retrieval instruction cannot be empty.", "INVALID_REQUEST")

    if len(request.instruction) > MAX_INSTRUCTION_LENGTH:
        raise IntakeValidationError(
            "Retrieval instruction exceeds maximum allowed length.", "REQUEST_TOO_LARGE"
        )

    if request.source_type not in CLIENT_ALLOWED_SOURCES:
        raise IntakeValidationError(
            f"source_type {request.source_type.value} cannot be set by a client.",
            "SOURCE_NOT_ALLOWED",
        )

    caller_request_id = getattr(request.lifecycle, "request_id", None)
    if caller_request_id and len(caller_request_id) > MAX_REQUEST_ID_LENGTH:
        raise IntakeValidationError(
            f"lifecycle.request_id exceeds {MAX_REQUEST_ID_LENGTH} characters.", "INVALID_LIFECYCLE"
        )

    for name, value in (
        ("correlation_id", getattr(request.lifecycle, "correlation_id", None)),
        ("idempotency_key", getattr(request.lifecycle, "idempotency_key", None)),
        ("parent_request_id", getattr(request.lifecycle, "parent_request_id", None)),
    ):
        if value is not None and (not isinstance(value, str) or len(value) > MAX_ID_LENGTH):
            raise IntakeValidationError(f"{name} is too long.", "INVALID_LIFECYCLE")

    deadline = getattr(request.lifecycle, "deadline", None)
    if deadline is not None and deadline <= _now_like(deadline):
        raise IntakeValidationError("The request deadline has already passed.", "DEADLINE_EXCEEDED")