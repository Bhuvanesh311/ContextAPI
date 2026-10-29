from __future__ import annotations

import logging
from time import perf_counter
from typing import Any, Callable, TypeVar

from app.knowledge.security.stage_3.context import (
    ValidationContext,
)
from app.knowledge.security.stage_3.exceptions import (
    StageThreeValidationError,
)

logger = logging.getLogger(
    "knowledge.security.stage_3",
)

T = TypeVar("T")


# ============================================================
# Base Structured Log Data
# ============================================================


def _base_log_data(
    context: ValidationContext,
) -> dict[str, Any]:
    """
    Build common structured log data for Stage 3.

    IMPORTANT

    Never use reserved logging.LogRecord keys such as:

        filename
        pathname
        module
        funcName
        lineno
        process
        thread
        message
        name
    """

    return {
        "upload_id": context.upload_id,
        "project_id": context.project_id,
        "document_id": context.document_id,
        "security_stage": context.stage,
        "validation_phase": context.current_phase,
        "validation_check": context.current_check,
        "document_filename": context.original_filename,
    }


# ============================================================
# Stage Logging
# ============================================================


def log_stage_started(
    context: ValidationContext,
) -> None:
    """
    Log the beginning of Stage 3.
    """

    logger.info(
        "Stage 3 validation started | document=%s",
        context.document_id,
        extra={
            **_base_log_data(context),
            "event": "stage_started",
            "status": "running",
        },
    )


def log_stage_passed(
    context: ValidationContext,
    duration_ms: float,
) -> None:
    """
    Log successful completion of Stage 3.
    """

    logger.info(
        "Stage 3 validation passed | document=%s | duration=%.3fms",
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
    context: ValidationContext,
    *,
    exception: Exception,
    duration_ms: float,
) -> None:
    """
    Log Stage 3 failure.
    """

    code = getattr(
        exception,
        "code",
        None,
    )

    logger.warning(
        (
            "Stage 3 validation failed | "
            "document=%s | phase=%s | check=%s | "
            "%s: %s | code=%s | duration=%.3fms"
        ),
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
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )


    # ============================================================
# Phase Logging
# ============================================================


def log_phase_started(
    context: ValidationContext,
    phase_name: str,
) -> None:
    """
    Log the beginning of a validation phase.
    """

    context.current_phase = phase_name
    context.current_check = None

    logger.info(
        "Stage 3 phase started: %s",
        phase_name,
        extra={
            **_base_log_data(context),
            "event": "phase_started",
            "status": "running",
        },
    )


def log_phase_completed(
    context: ValidationContext,
) -> None:
    """
    Log successful completion of the current phase.
    """

    logger.info(
        "Stage 3 phase completed: %s",
        context.current_phase,
        extra={
            **_base_log_data(context),
            "event": "phase_completed",
            "status": "passed",
        },
    )


# ============================================================
# Check Logging
# ============================================================


def log_check_started(
    context: ValidationContext,
) -> None:
    """
    Log the beginning of a validation check.
    """

    logger.info(
        "Stage 3 check started: %s",
        context.current_check,
        extra={
            **_base_log_data(context),
            "event": "check_started",
            "status": "running",
        },
    )


def log_check_passed(
    context: ValidationContext,
    duration_ms: float,
) -> None:
    """
    Log a successful validation check.
    """

    logger.info(
        "Stage 3 check passed: %s | %.3fms",
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
    context: ValidationContext,
    *,
    exception: Exception,
    duration_ms: float,
) -> None:
    """
    Log a failed validation check.
    """

    code = getattr(
        exception,
        "code",
        None,
    )

    logger.warning(
        (
            "Stage 3 check failed: %s | "
            "%s: %s | code=%s | %.3fms"
        ),
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
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "duration_ms": round(
                duration_ms,
                3,
            ),
        },
    )   


    # ============================================================
# Logged Check Executor
# ============================================================


def run_logged_check(
    context: ValidationContext,
    check_name: str,
    check: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Execute a validation check with standardized logging,
    timing and exception handling.
    """

    context.current_check = check_name

    log_check_started(
        context,
    )

    started = perf_counter()

    try:

        result = check(
            context,
            *args,
            **kwargs,
        )

    except StageThreeValidationError as exc:

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
            (
                "Unexpected Stage 3 exception | "
                "document=%s | phase=%s | check=%s"
            ),
            context.document_id,
            context.current_phase,
            context.current_check,
            extra={
                **_base_log_data(context),
                "event": "unexpected_exception",
                "status": "error",
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
        )

        raise

    duration_ms = (
        perf_counter()
        - started
    ) * 1000

    log_check_passed(
        context,
        duration_ms,
    )

    return result