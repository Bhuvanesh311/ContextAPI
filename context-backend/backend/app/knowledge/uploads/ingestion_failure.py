from dataclasses import dataclass

from app.core.enums import IngestionStage


class FailureCategory:
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


@dataclass(frozen=True)
class IngestionFailure:
    category: str
    error_code: str
    message: str
    stage: IngestionStage
    details: dict | None = None


RETRYABLE_ERROR_CODES = {
    "STORAGE_TEMPORARY_ERROR",
    "STORAGE_TIMEOUT",
    "STORAGE_UNAVAILABLE",
    "PARSER_TIMEOUT",
    "PARSER_PROCESS_CRASH",
    "PARSER_TEMPORARY_ERROR",
    "DATABASE_TEMPORARY_ERROR",
    "DATABASE_CONNECTION_ERROR",
    "NETWORK_TIMEOUT",
    "NETWORK_ERROR",
    "SERVICE_UNAVAILABLE",
}

PERMANENT_ERROR_CODES = {
    "SECURITY_REJECTED",
    "SECURITY_REVIEW_REQUIRED",
    "MALICIOUS_ARTIFACT",
    "INVALID_ARTIFACT",
    "UNSUPPORTED_FORMAT",
    "FORMAT_VALIDATION_FAILED",
    "PARSER_NOT_FOUND",
    "PARSER_VALIDATION_FAILED",
    "ARTIFACT_NOT_FOUND",
    "INVALID_CONFIGURATION",
}


def classify_failure(
    *,
    stage: IngestionStage,
    error_code: str,
    message: str,
    details: dict | None = None,
) -> IngestionFailure:

    if error_code in PERMANENT_ERROR_CODES:
        category = FailureCategory.PERMANENT

    elif error_code in RETRYABLE_ERROR_CODES:
        category = FailureCategory.RETRYABLE

    else:
        category = FailureCategory.RETRYABLE

    return IngestionFailure(
        category=category,
        error_code=error_code,
        message=message,
        stage=stage,
        details=details,
    )


def is_retryable(
    error_code: str,
) -> bool:

    if error_code in PERMANENT_ERROR_CODES:
        return False

    return True


def is_permanent(
    error_code: str,
) -> bool:

    return error_code in PERMANENT_ERROR_CODES