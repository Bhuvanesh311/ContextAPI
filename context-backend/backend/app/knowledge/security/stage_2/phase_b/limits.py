from app.knowledge.security.stage_2.constants import (
    MAX_ARCHIVE_DEPTH,
    MAX_ARCHIVE_ENTRIES,
    MAX_SINGLE_ENTRY_SIZE,
    MAX_TOTAL_EXTRACTED_SIZE,
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveDepthExceededError,
    EntrySizeExceededError,
    ExtractedSizeExceededError,
    FileCountExceededError,
)


def validate_archive_depth(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "archive_depth_validation"

    if context.archive_depth < 0:
        raise ArchiveDepthExceededError(
            (
                f"Invalid archive depth "
                f"'{context.archive_depth}'."
            ),
            phase=PHASE_SECURITY,
            check="archive_depth_validation",
            code="INVALID_ARCHIVE_DEPTH",
        )

    if context.archive_depth > MAX_ARCHIVE_DEPTH:
        raise ArchiveDepthExceededError(
            (
                f"Archive depth {context.archive_depth} exceeds "
                f"maximum allowed depth "
                f"{MAX_ARCHIVE_DEPTH}."
            ),
            phase=PHASE_SECURITY,
            check="archive_depth_validation",
            code="ARCHIVE_DEPTH_EXCEEDED",
            details={
                "archive_depth": context.archive_depth,
                "maximum": MAX_ARCHIVE_DEPTH,
            },
        )


def validate_entry_count(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "archive_entry_count_validation"

    if context.entry_count > MAX_ARCHIVE_ENTRIES:
        raise FileCountExceededError(
            (
                f"Archive contains {context.entry_count} entries, "
                f"exceeding the maximum allowed "
                f"{MAX_ARCHIVE_ENTRIES}."
            ),
            phase=PHASE_SECURITY,
            check="archive_entry_count_validation",
            code="ARCHIVE_ENTRY_COUNT_EXCEEDED",
            details={
                "entry_count": context.entry_count,
                "maximum": MAX_ARCHIVE_ENTRIES,
            },
        )


def validate_single_entry_sizes(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "single_entry_size_validation"

    for entry in context.entries:

        if not entry.is_file:
            continue

        if entry.uncompressed_size < 0:
            raise EntrySizeExceededError(
                (
                    f"Archive entry '{entry.name}' reports "
                    f"an invalid negative size."
                ),
                phase=PHASE_SECURITY,
                check="single_entry_size_validation",
                code="INVALID_ENTRY_SIZE",
                details={
                    "entry": entry.name,
                    "size": entry.uncompressed_size,
                },
            )

        if entry.uncompressed_size > MAX_SINGLE_ENTRY_SIZE:
            raise EntrySizeExceededError(
                (
                    f"Archive entry '{entry.name}' expands to "
                    f"{entry.uncompressed_size} bytes, exceeding "
                    f"the maximum allowed "
                    f"{MAX_SINGLE_ENTRY_SIZE} bytes."
                ),
                phase=PHASE_SECURITY,
                check="single_entry_size_validation",
                code="ENTRY_SIZE_EXCEEDED",
                details={
                    "entry": entry.name,
                    "size": entry.uncompressed_size,
                    "maximum": MAX_SINGLE_ENTRY_SIZE,
                },
            )


def validate_total_extracted_size(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "total_extracted_size_validation"

    # Recalculate from normalized entries instead of blindly
    # trusting the aggregate field.
    total_size = sum(
        entry.uncompressed_size
        for entry in context.entries
        if entry.is_file
    )

    if total_size < 0:
        raise ExtractedSizeExceededError(
            "Archive reports an invalid extracted size.",
            phase=PHASE_SECURITY,
            check="total_extracted_size_validation",
            code="INVALID_EXTRACTED_SIZE",
        )

    context.estimated_extracted_size = total_size

    if total_size > MAX_TOTAL_EXTRACTED_SIZE:
        raise ExtractedSizeExceededError(
            (
                f"Archive would extract to approximately "
                f"{total_size} bytes, exceeding the maximum "
                f"allowed {MAX_TOTAL_EXTRACTED_SIZE} bytes."
            ),
            phase=PHASE_SECURITY,
            check="total_extracted_size_validation",
            code="TOTAL_EXTRACTED_SIZE_EXCEEDED",
            details={
                "estimated_size": total_size,
                "maximum": MAX_TOTAL_EXTRACTED_SIZE,
            },
        )


def validate_resource_limits(
    context: ArchiveValidationContext,
) -> None:
    """
    Run the complete metadata-based resource policy.
    """

    validate_archive_depth(context)
    validate_entry_count(context)
    validate_single_entry_sizes(context)
    validate_total_extracted_size(context)