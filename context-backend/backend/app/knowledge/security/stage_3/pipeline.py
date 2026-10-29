from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from app.knowledge.security.stage_3.audit.logger import (
    log_phase_started,
    log_stage_failed,
    log_stage_passed,
    log_stage_started,
    run_logged_check,
)
from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.phase_a.format import (
    identify_document_format,
)
from app.knowledge.security.stage_3.phase_b.selector import (
    select_validator,
)
from app.knowledge.security.stage_3.phase_c.decision import (
    approve_for_parsing,
)


def run_stage_three(
    context: ValidationContext,
    *,
    persist_callback: Callable[..., Any] | None = None,
    queue_callback: Callable[..., Any] | None = None,
) -> ValidationContext:
    """
    Execute Stage 3 - Format Specific Security Validation.

    Flow

        Phase A
            Format Identification

        Phase B
            Validator Selection
            Format Validation

        Phase C
            Parser Admission Decision
    """

    started = perf_counter()

    log_stage_started(
        context,
    )

    try:

        # ===================================================
        # Phase A
        # ===================================================

        log_phase_started(
            context,
            "format_identification",
        )

        run_logged_check(
            context,
            "format_detection",
            identify_document_format,
        )

        # ===================================================
        # Phase B
        # ===================================================

        log_phase_started(
            context,
            "format_security_validation",
        )

        validator = run_logged_check(
            context,
            "validator_selection",
            select_validator,
        )

        run_logged_check(
            context,
            context.validator_name,
            validator,
        )

        context.security_validated = True

        # ===================================================
        # Phase C
        # ===================================================

        log_phase_started(
            context,
            "parser_admission",
        )

        run_logged_check(
            context,
            "admission_decision",
            approve_for_parsing,
        )

        context.ready_for_sandbox = True

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_stage_passed(
            context,
            duration_ms,
        )

        if persist_callback is not None:

            persist_callback(
                context,
            )

        if queue_callback is not None:

            queue_callback(
                context,
            )

        return context

    except Exception as exc:

        duration_ms = (
            perf_counter()
            - started
        ) * 1000

        log_stage_failed(
            context,
            exception=exc,
            duration_ms=duration_ms,
        )

        raise