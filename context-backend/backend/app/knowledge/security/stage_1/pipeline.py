from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter

from app.knowledge.security.stage_1.constants import (
    PHASE_IDENTITY_METADATA,
    PHASE_INTEGRITY_TRUST,
    PHASE_SECURITY,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_RUNNING,
)
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import (
    StageOnePipelineError,
    StageOneValidationError,
)

from app.knowledge.security.stage_1.phase_a.identity import (
    validate_file_identity,
)
from app.knowledge.security.stage_1.phase_a.metadata import (
    collect_file_metadata,
)

from app.knowledge.security.stage_1.phase_b.MIME import (
    detect_mime_type,
)
from app.knowledge.security.stage_1.phase_b.signature import (
    validate_file_signature,
)
from app.knowledge.security.stage_1.phase_b.hashing import (
    generate_file_hash,
)
from app.knowledge.security.stage_1.phase_b.duplicate import (
    check_duplicate_file,
)
from app.knowledge.security.stage_1.phase_b.Compatibility import (
    validate_file_compatibility,
)

from app.knowledge.security.stage_1.phase_c.content import (
    detect_content_type,
)
from app.knowledge.security.stage_1.phase_c.encoding import (
    detect_encoding,
)
from app.knowledge.security.stage_1.phase_c.entropy import (
    analyze_entropy,
)
from app.knowledge.security.stage_1.phase_c.malware import (
    scan_for_malware,
)
from app.knowledge.security.stage_1.phase_c.storage import (
    verify_storage,
)

from app.knowledge.security.stage_1.audit.logger import (
    log_stage_started,
    log_stage_passed,
    log_stage_failed,
    log_phase_started,
    run_logged_check,
)


DuplicateLookup = Callable[[str, str, str], str | None]


def run_stage_one(context: ValidationContext,lookup_duplicate: DuplicateLookup,) -> ValidationContext:
    """
    Execute Stage 1 - Universal Validation.

    Execution order:

        Phase A - Identity & Metadata
            Identity validation
            Metadata collection

        Phase B - Integrity & Trust
            MIME detection
            Signature validation
            MIME/signature compatibility
            SHA-256 generation
            Duplicate detection

        Phase C - Security
            Binary/text classification
            Encoding detection
            Entropy analysis
            Malware scanning
            Storage verification

    Every validation check is executed through run_logged_check()
    so that check start, success, failure, and execution duration
    are logged consistently.

    StageOneValidationError is re-raised when an expected
    validation failure occurs.

    Unexpected exceptions are converted into
    StageOnePipelineError.
    """

    context.status = STATUS_RUNNING
    context.started_at = datetime.now(timezone.utc)

    stage_started = perf_counter()

    log_stage_started(context)

    try:

        # ---------------------------------------------------------
        # Phase A - Identity & Metadata
        # ---------------------------------------------------------

        context.current_phase = PHASE_IDENTITY_METADATA

        log_phase_started(context)

        run_logged_check(
            context,
            "file_identity",
            validate_file_identity,
        )

        run_logged_check(
            context,
            "metadata_collection",
            collect_file_metadata,
        )

        # ---------------------------------------------------------
        # Phase B - Integrity & Trust
        # ---------------------------------------------------------

        context.current_phase = PHASE_INTEGRITY_TRUST

        log_phase_started(context)

        run_logged_check(
            context,
            "mime_detection",
            detect_mime_type,
        )

        run_logged_check(
            context,
            "magic_signature",
            validate_file_signature,
        )

        run_logged_check(
            context,
            "mime_signature_matching",
            validate_file_compatibility,
        )

        run_logged_check(
            context,
            "hash_generation",
            generate_file_hash,
        )

        run_logged_check(
            context,
            "duplicate_detection",
            check_duplicate_file,
            lookup_duplicate,
        )

        # ---------------------------------------------------------
        # Phase C - Security
        # ---------------------------------------------------------

        context.current_phase = PHASE_SECURITY

        log_phase_started(context)

        run_logged_check(
            context,
            "binary_text_detection",
            detect_content_type,
        )

        run_logged_check(
            context,
            "encoding_detection",
            detect_encoding,
        )

        run_logged_check(
            context,
            "entropy_analysis",
            analyze_entropy,
        )

        run_logged_check(
            context,
            "malware_scan",
            scan_for_malware,
        )

        run_logged_check(
            context,
            "storage_verification",
            verify_storage,
        )

        # ---------------------------------------------------------
        # Stage 1 Passed
        # ---------------------------------------------------------

        context.status = STATUS_PASSED
        context.current_phase = None
        context.current_check = None
        context.completed_at = datetime.now(timezone.utc)

        duration_ms = (
            perf_counter() - stage_started
        ) * 1000

        log_stage_passed(
            context,
            duration_ms=duration_ms,
        )

        return context

    except StageOneValidationError as exc:

        # ---------------------------------------------------------
        # Expected validation failure
        # ---------------------------------------------------------

        context.status = STATUS_FAILED

        context.failure_code = exc.code
        context.failure_reason = exc.message

        if exc.phase:
            context.current_phase = exc.phase

        if exc.check:
            context.current_check = exc.check

        context.completed_at = datetime.now(timezone.utc)

        duration_ms = (
            perf_counter() - stage_started
        ) * 1000

        log_stage_failed(
            context,
            code=exc.code,
            duration_ms=duration_ms,
        )

        raise

    except Exception as exc:

        # ---------------------------------------------------------
        # Unexpected internal failure
        # ---------------------------------------------------------

        context.status = STATUS_FAILED

        context.failure_code = "STAGE_ONE_INTERNAL_ERROR"
        context.failure_reason = (
            "Stage 1 encountered an internal error."
        )

        context.completed_at = datetime.now(timezone.utc)

        duration_ms = (
            perf_counter() - stage_started
        ) * 1000

        log_stage_failed(
            context,
            code="STAGE_ONE_INTERNAL_ERROR",
            duration_ms=duration_ms,
        )

        raise StageOnePipelineError(
            "Stage 1 Universal Validation failed because of an "
            "unexpected internal error.",
            phase=context.current_phase,
            check=context.current_check,
            code="STAGE_ONE_INTERNAL_ERROR",
        ) from exc