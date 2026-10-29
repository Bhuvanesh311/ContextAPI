from collections.abc import Callable
from time import perf_counter
from typing import Any

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    StageTwoError,
)

from app.knowledge.security.stage_2.constants import (
    PHASE_IDENTITY_METADATA,
    PHASE_SECURITY,
    PHASE_EXTRACTION,
    PHASE_ORCHESTRATION,
)


# ============================================================
# Audit Logger
# ============================================================

from app.knowledge.security.stage_2.audit.logger import (
    log_stage_started,
    log_stage_passed,
    log_stage_failed,
    log_phase_started,
    run_logged_check,
)


# ============================================================
# Phase A
# ============================================================

from app.knowledge.security.stage_2.phase_a.detection import (
    detect_archive_type,
)
from app.knowledge.security.stage_2.phase_a.format import (
    validate_archive_format,
)
from app.knowledge.security.stage_2.phase_a.metadata import (
    collect_archive_metadata,
)


# ============================================================
# Phase B
# ============================================================

from app.knowledge.security.stage_2.phase_b.integrity import (
    validate_archive_integrity,
)
from app.knowledge.security.stage_2.phase_b.limits import (
    validate_resource_limits,
)
from app.knowledge.security.stage_2.phase_b.bomb import (
    detect_archive_bomb,
)
from app.knowledge.security.stage_2.phase_b.encryption import (
    validate_encryption_policy,
)
from app.knowledge.security.stage_2.phase_b.paths import (
    validate_archive_paths,
)
from app.knowledge.security.stage_2.phase_b.links import (
    validate_archive_links,
)
from app.knowledge.security.stage_2.phase_b.entries import (
    validate_archive_entries,
)
from app.knowledge.security.stage_2.phase_b.filename import (
    validate_archive_filenames,
)


# ============================================================
# Phase C
# ============================================================

from app.knowledge.security.stage_2.phase_c.workspace import (
    create_secure_workspace,
)
from app.knowledge.security.stage_2.phase_c.extraction import (
    extract_archive_securely,
)
from app.knowledge.security.stage_2.phase_c.metadata import (
    collect_extracted_metadata,
)
from app.knowledge.security.stage_2.phase_c.report import (
    build_extraction_report,
)


# ============================================================
# Phase D
# ============================================================

from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)
from app.knowledge.security.stage_2.phase_d.orchestration import (
    orchestrate_children,
)
from app.knowledge.security.stage_2.phase_d.summary import (
    build_orchestration_summary,
)


# ============================================================
# Infrastructure callback contracts
# ============================================================

PersistCallback = Callable[
    [ChildFileContext],
    str,
]

QueueCallback = Callable[
    [ChildFileContext],
    None,
]


# ============================================================
# Stage 2 Pipeline
# ============================================================

def run_stage_two(
    context: ArchiveValidationContext,
    *,
    persist_callback: PersistCallback,
    queue_callback: QueueCallback,
) -> dict[str, Any]:
    """
    Execute complete Stage 2 archive validation.

    Phase A:
        Archive identity and metadata

    Phase B:
        Archive security validation

    Phase C:
        Controlled extraction

    Phase D:
        Child orchestration
    """

    # Start timing the entire Stage 2 pipeline.
    stage_started = perf_counter()

    log_stage_started(
        context
    )

    try:

        # ====================================================
        # PHASE A — Archive Identity & Metadata
        # ====================================================

        log_phase_started(
            context,
            PHASE_IDENTITY_METADATA,
        )

        run_logged_check(
            context,
            "archive_type_detection",
            detect_archive_type,
        )

        run_logged_check(
            context,
            "archive_format_validation",
            validate_archive_format,
        )

        run_logged_check(
            context,
            "archive_metadata_collection",
            collect_archive_metadata,
        )


        # ====================================================
        # PHASE B — Archive Security
        # ====================================================

        log_phase_started(
            context,
            PHASE_SECURITY,
        )

        run_logged_check(
            context,
            "archive_integrity_validation",
            validate_archive_integrity,
        )

        run_logged_check(
            context,
            "archive_resource_limits",
            validate_resource_limits,
        )

        run_logged_check(
            context,
            "archive_bomb_detection",
            detect_archive_bomb,
        )

        run_logged_check(
            context,
            "archive_encryption_policy",
            validate_encryption_policy,
        )

        run_logged_check(
            context,
            "archive_path_validation",
            validate_archive_paths,
        )

        run_logged_check(
            context,
            "archive_link_validation",
            validate_archive_links,
        )

        run_logged_check(
            context,
            "archive_entry_validation",
            validate_archive_entries,
        )

        run_logged_check(
            context,
            "archive_filename_validation",
            validate_archive_filenames,
        )


        # ====================================================
        # PHASE C — Controlled Extraction
        # ====================================================

        log_phase_started(
            context,
            PHASE_EXTRACTION,
        )

        run_logged_check(
            context,
            "secure_workspace_creation",
            create_secure_workspace,
        )

        run_logged_check(
            context,
            "secure_archive_extraction",
            extract_archive_securely,
        )

        run_logged_check(
            context,
            "extracted_metadata_collection",
            collect_extracted_metadata,
        )

        extraction_report = run_logged_check(
            context,
            "extraction_report_generation",
            build_extraction_report,
        )


        # ====================================================
        # PHASE D — Child Orchestration
        # ====================================================

        log_phase_started(
            context,
            PHASE_ORCHESTRATION,
        )

        children = run_logged_check(
            context,
            "child_orchestration",
            orchestrate_children,
            persist_callback=persist_callback,
            queue_callback=queue_callback,
        )

        orchestration_summary = run_logged_check(
            context,
            "orchestration_summary_generation",
            build_orchestration_summary,
            children,
        )


    # ========================================================
    # Stage 2 failed with one of OUR known exceptions
    # ========================================================

    except StageTwoError as exc:

        duration_ms = (
            perf_counter() - stage_started
        ) * 1000

        log_stage_failed(
            context,
            exception=exc,
            duration_ms=duration_ms,
        )

        # Do NOT swallow the exception.
        # tasks.py / runner.py still needs to handle it.
        raise


    # ========================================================
    # Unexpected programming/system failure
    # ========================================================

    except Exception as exc:

        duration_ms = (
            perf_counter() - stage_started
        ) * 1000

        log_stage_failed(
            context,
            exception=exc,
            duration_ms=duration_ms,
        )

        raise


    # ========================================================
    # Entire Stage 2 passed
    # ========================================================

    duration_ms = (
        perf_counter() - stage_started
    ) * 1000

    log_stage_passed(
        context,
        duration_ms,
    )

    return {
        "extraction": extraction_report,
        "orchestration": orchestration_summary,
    }