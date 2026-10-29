import math

from app.knowledge.security.stage_2.constants import (
    MAX_COMPRESSION_RATIO,
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveBombError,
    CompressionRatioExceededError,
)


def _calculate_ratio(
    compressed_size: int,
    uncompressed_size: int,
) -> float:
    """
    Calculate uncompressed / compressed ratio.

    Empty files are harmless.

    A non-empty file claiming zero compressed bytes is treated
    as an infinite ratio and therefore suspicious.
    """

    if uncompressed_size <= 0:
        return 0.0

    if compressed_size <= 0:
        return math.inf

    return uncompressed_size / compressed_size


def validate_entry_compression_ratios(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "entry_compression_ratio_validation"

    for entry in context.entries:

        if not entry.is_file:
            continue

        # TAR metadata does not necessarily expose a meaningful
        # compressed size per member. A zero value therefore
        # cannot automatically mean "bomb" for every format.
        if (
            context.archive_type is not None
            and context.archive_type.value in {"tar", "tar.gz"}
        ):
            continue

        ratio = _calculate_ratio(
            entry.compressed_size,
            entry.uncompressed_size,
        )

        if ratio > MAX_COMPRESSION_RATIO:
            raise CompressionRatioExceededError(
                (
                    f"Archive entry '{entry.name}' has a "
                    f"compression ratio of {ratio:.2f}:1, "
                    f"exceeding the maximum allowed "
                    f"{MAX_COMPRESSION_RATIO:.2f}:1."
                ),
                phase=PHASE_SECURITY,
                check="entry_compression_ratio_validation",
                code="ENTRY_COMPRESSION_RATIO_EXCEEDED",
                details={
                    "entry": entry.name,
                    "compressed_size": entry.compressed_size,
                    "uncompressed_size": entry.uncompressed_size,
                    "ratio": ratio,
                    "maximum": MAX_COMPRESSION_RATIO,
                },
            )


def validate_archive_compression_ratio(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "archive_compression_ratio_validation"

    compressed = context.compressed_size
    uncompressed = context.estimated_extracted_size

    if uncompressed <= 0:
        context.compression_ratio = 0.0
        return

    # Some archive formats don't expose meaningful aggregate
    # compressed member sizes through our normalized metadata.
    if compressed <= 0:
        return

    ratio = _calculate_ratio(
        compressed,
        uncompressed,
    )

    context.compression_ratio = ratio

    if ratio > MAX_COMPRESSION_RATIO:
        raise ArchiveBombError(
            (
                f"Archive '{context.original_filename}' has a "
                f"compression ratio of {ratio:.2f}:1, exceeding "
                f"the maximum allowed "
                f"{MAX_COMPRESSION_RATIO:.2f}:1."
            ),
            phase=PHASE_SECURITY,
            check="archive_compression_ratio_validation",
            code="ARCHIVE_COMPRESSION_RATIO_EXCEEDED",
            details={
                "compressed_size": compressed,
                "uncompressed_size": uncompressed,
                "ratio": ratio,
                "maximum": MAX_COMPRESSION_RATIO,
            },
        )


def detect_archive_bomb(
    context: ArchiveValidationContext,
) -> None:
    """
    Run compression-based bomb checks.

    IMPORTANT:
    Compression ratio is not our only protection.

    Resource limits separately enforce:
      - entry count
      - single-entry size
      - total extracted size
      - nesting depth
    """

    validate_entry_compression_ratios(context)
    validate_archive_compression_ratio(context)