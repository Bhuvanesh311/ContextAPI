import logging
from time import perf_counter
from typing import Any, Callable, TypeVar

from app.knowledge.security.stage_1.context import (
    ValidationContext,
)
from app.knowledge.security.stage_1.exceptions import (
    StageOneValidationError,
)


logger = logging.getLogger(
    "knowledge.security.stage_1"
)

T = TypeVar("T")


# ============================================================
# Base structured log data
# ============================================================


def _base_log_data(
    context: ValidationContext,
) -> dict[str, Any]:

    return {
        "upload_id": context.upload_id,
        "project_id": context.project_id,
        "document_id": context.document_id,
        "stage": "stage_1",
        "phase": context.current_phase,
        "check": context.current_check,
    }


# ============================================================
# Stage logging
# ============================================================


def log_stage_started(
    context: ValidationContext,
) -> None:

    logger.info(
        "Stage 1 validation started | "
        "document=%s",
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

    logger.info(
        "Stage 1 validation passed | "
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
    context: ValidationContext,
    *,
    code: str | None,
    duration_ms: float,
) -> None:

    logger.warning(
        "Stage 1 validation failed | "
        "document=%s | phase=%s | check=%s | "
        "code=%s | duration=%.3fms",
        context.document_id,
        context.current_phase,
        context.current_check,
        code,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "stage_failed",
            "status": "failed",
            "error_code": code,
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
    context: ValidationContext,
) -> None:

    logger.info(
        "Stage 1 phase started: %s",
        context.current_phase,
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
    context: ValidationContext,
) -> None:

    logger.info(
        "Stage 1 check started: %s",
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

    logger.info(
        "Stage 1 check passed: %s | %.3fms",
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
    code: str | None,
    duration_ms: float,
    exception: Exception | None = None,
) -> None:

    if exception is not None:

        logger.warning(
            "Stage 1 check failed: %s | "
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
                "exception_message": (
                    str(exception)
                ),
                "duration_ms": round(
                    duration_ms,
                    3,
                ),
            },
        )

        return

    logger.warning(
        "Stage 1 check failed: %s | "
        "code=%s | %.3fms",
        context.current_check,
        code,
        duration_ms,
        extra={
            **_base_log_data(context),
            "event": "check_failed",
            "status": "failed",
            "error_code": code,
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
    context: ValidationContext,
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
    # Expected Stage 1 validation/security exception
    # --------------------------------------------------------

    except StageOneValidationError as exc:

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_check_failed(
            context,
            code=exc.code,
            duration_ms=duration_ms,
            exception=exc,
        )

        raise

    # --------------------------------------------------------
    # Unexpected implementation/infrastructure exception
    # --------------------------------------------------------

    except Exception as exc:

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_check_failed(
            context,
            code="UNEXPECTED_CHECK_ERROR",
            duration_ms=duration_ms,
            exception=exc,
        )

        logger.exception(
            "Unexpected Stage 1 check exception | "
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
                    "UNEXPECTED_CHECK_ERROR"
                ),
                "exception_type": (
                    type(exc).__name__
                ),
                "exception_message": str(exc),
            },
        )

        raise

    # --------------------------------------------------------
    # PASS
    # --------------------------------------------------------

    duration_ms = (
        perf_counter()
        - started
    ) * 1000

    log_check_passed(
        context,
        duration_ms=duration_ms,
    )

    return result