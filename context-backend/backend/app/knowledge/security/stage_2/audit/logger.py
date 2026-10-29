import logging
from time import perf_counter
from typing import Any, Callable, TypeVar

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    StageTwoError,
)


logger = logging.getLogger(
    "knowledge.security.stage_2"
)

T = TypeVar("T")


# ============================================================
# Base structured log data
# ============================================================


def _base_log_data(
    context: ArchiveValidationContext,
) -> dict[str, Any]:
    """
    Common structured fields attached to Stage 2 log records.

    Important:
    Do not use reserved logging.LogRecord attribute names
    such as:
        filename
        pathname
        module
        funcName
        lineno
        levelname
        message
        name
        created
        thread
        process
    """

    return {
        "upload_id": context.upload_id,
        "project_id": context.project_id,
        "document_id": context.document_id,

        "security_stage": "stage_2",

        "validation_phase": getattr(
            context,
            "current_phase",
            None,
        ),

        "validation_check": getattr(
            context,
            "current_check",
            None,
        ),

        "archive_depth": context.archive_depth,

        # Do NOT call this "filename".
        # filename is reserved by logging.LogRecord.
        "archive_filename": (
            context.original_filename
        ),
    }

# ============================================================
# Stage logging
# ============================================================


def log_stage_started(
    context: ArchiveValidationContext,
) -> None:

    logger.info(
        "Stage 2 validation started | "
        "document=%s | filename=%s | depth=%s",
        context.document_id,
        context.original_filename,
        context.archive_depth,
        extra={
            **_base_log_data(context),
            "event": "stage_started",
            "status": "running",
        },
    )


def log_stage_passed(
    context: ArchiveValidationContext,
    duration_ms: float,
) -> None:

    logger.info(
        "Stage 2 validation passed | "
        "document=%s | duration=%.3fms",
        context.document_id,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "stage_completed",
            "status": "passed",
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )


def log_stage_failed(
    context: ArchiveValidationContext,
    *,
    exception: Exception,
    duration_ms: float,
) -> None:

    code = getattr(
        exception,
        "code",
        None,
    )

    logger.warning(
        "Stage 2 validation failed | "
        "document=%s | phase=%s | check=%s | "
        "%s: %s | code=%s | duration=%.3fms",
        context.document_id,
        context.current_phase,
        context.current_check,
        type(exception).__name__,
        str(exception),
        code,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "stage_failed",
            "status": "failed",
            "error_code": code,
            "exception_type": (
                type(exception).__name__
            ),
            "exception_message": str(
                exception
            ),
            "error_details": getattr(
                exception,
                "details",
                {},
            ),
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )


# ============================================================
# Phase logging
# ============================================================


def log_phase_started(
    context: ArchiveValidationContext,
    phase_name: str,
) -> None:

    context.current_phase = phase_name
    context.current_check = None

    logger.info(
        "Stage 2 phase started: %s",
        phase_name,
        extra={
            **_base_log_data(context),
            "event": "phase_started",
            "status": "running",
        },
    )


# ============================================================
# Check logging
# ============================================================


def log_check_started(
    context: ArchiveValidationContext,
) -> None:

    logger.info(
        "Stage 2 check started: %s",
        context.current_check,
        extra={
            **_base_log_data(context),
            "event": "check_started",
            "status": "running",
        },
    )


def log_check_passed(
    context: ArchiveValidationContext,
    duration_ms: float,
) -> None:

    logger.info(
        "Stage 2 check passed: %s | %.3fms",
        context.current_check,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "check_completed",
            "status": "passed",
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )


def log_check_failed(
    context: ArchiveValidationContext,
    *,
    exception: Exception,
    duration_ms: float,
) -> None:

    code = getattr(
        exception,
        "code",
        None,
    )

    logger.warning(
        "Stage 2 check failed: %s | "
        "%s: %s | code=%s | %.3fms",
        context.current_check,
        type(exception).__name__,
        str(exception),
        code,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "check_failed",
            "status": "failed",
            "error_code": code,
            "exception_type": (
                type(exception).__name__
            ),
            "exception_message": str(
                exception
            ),
            "error_details": getattr(
                exception,
                "details",
                {},
            ),
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )


# ============================================================
# Logged check executor
# ============================================================


def run_logged_check(
    context: ArchiveValidationContext,
    check_name: str,
    check: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:

    context.current_check = check_name

    log_check_started(
        context
    )

    started = perf_counter()

    try:

        result = check(
            context,
            *args,
            **kwargs,
        )

    # --------------------------------------------------------
    # Known Stage 2 exception
    # --------------------------------------------------------

    except StageTwoError as exc:

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_check_failed(
            context,
            exception=exc,
            duration_ms=duration_ms,
        )

        raise

    # --------------------------------------------------------
    # Unexpected exception
    # --------------------------------------------------------

    except Exception as exc:

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_check_failed(
            context,
            exception=exc,
            duration_ms=duration_ms,
        )

        logger.exception(
            "Unexpected Stage 2 check exception | "
            "document=%s | phase=%s | check=%s",
            context.document_id,
            context.current_phase,
            context.current_check,
            extra={
                **_base_log_data(context),
                "event": (
                    "unexpected_check_exception"
                ),
                "status": "error",
                "error_code": (
                    "UNEXPECTED_STAGE_TWO_ERROR"
                ),
                "exception_type": (
                    type(exc).__name__
                ),
                "exception_message": str(exc),
            },
        )

        raise

    # --------------------------------------------------------
    # Passed
    # --------------------------------------------------------

    duration_ms = (
        perf_counter()
        - started
    ) * 1000

    log_check_passed(
        context,
        duration_ms,
    )

    return result