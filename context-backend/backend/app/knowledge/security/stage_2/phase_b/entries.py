from app.knowledge.security.stage_2.constants import (
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    DuplicateEntryError,
    EmptyArchiveError,
    UnsupportedEntryError,
)


def _canonical_entry_name(name: str) -> str:
    """
    Create a normalized representation of an archive entry name
    for duplicate detection.

    This function does NOT resolve '..'. Path traversal is handled
    separately by paths.py.
    """

    normalized = name.replace("\\", "/")

    # Remove harmless leading "./"
    while normalized.startswith("./"):
        normalized = normalized[2:]

    # Normalize repeated separators.
    while "//" in normalized:
        normalized = normalized.replace("//", "/")

    # Treat "folder" and "folder/" as the same logical path.
    normalized = normalized.rstrip("/")

    return normalized


def validate_empty_archive(
    context: ArchiveValidationContext,
) -> None:
    """
    Reject archives containing no usable payload entries.

    Examples rejected:
        empty.zip

        directories_only.zip
        └── folder/
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "empty_archive_validation"

    # Completely empty archive.
    if not context.entries:
        raise EmptyArchiveError(
            (
                f"Archive '{context.original_filename}' "
                f"contains no entries."
            ),
            phase=PHASE_SECURITY,
            check="empty_archive_validation",
            code="EMPTY_ARCHIVE",
            details={
                "filename": context.original_filename,
                "entry_count": 0,
            },
        )

    # An archive containing only directories is also useless
    # for our ingestion pipeline.
    payload_entries = [
        entry
        for entry in context.entries
        if (
            entry.is_file
            or entry.is_symlink
            or entry.is_hardlink
        )
    ]

    if not payload_entries:
        raise EmptyArchiveError(
            (
                f"Archive '{context.original_filename}' "
                f"contains no usable file entries."
            ),
            phase=PHASE_SECURITY,
            check="empty_archive_validation",
            code="ARCHIVE_WITHOUT_FILES",
            details={
                "filename": context.original_filename,
                "entry_count": len(context.entries),
            },
        )


def validate_duplicate_entries(
    context: ArchiveValidationContext,
) -> None:
    """
    Reject duplicate archive paths.

    Examples:

        config.json
        config.json

    or:

        ./config.json
        config.json

    are treated as duplicate logical paths.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "duplicate_entry_validation"

    seen: dict[str, str] = {}

    for entry in context.entries:

        canonical_name = _canonical_entry_name(
            entry.name
        )

        if canonical_name in seen:
            raise DuplicateEntryError(
                (
                    f"Archive '{context.original_filename}' "
                    f"contains duplicate entry "
                    f"'{entry.name}'."
                ),
                phase=PHASE_SECURITY,
                check="duplicate_entry_validation",
                code="DUPLICATE_ARCHIVE_ENTRY",
                details={
                    "entry": entry.name,
                    "first_entry": seen[canonical_name],
                    "canonical_name": canonical_name,
                },
            )

        seen[canonical_name] = entry.name


def validate_supported_entries(
    context: ArchiveValidationContext,
) -> None:
    """
    Ensure every archive member has exactly one known entry type.

    Known types:
        regular file
        directory
        symbolic link
        hard link

    Symlinks and hard links are recognized here as valid archive
    entry TYPES, but links.py will reject them according to our
    security policy.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "unsupported_entry_validation"

    for entry in context.entries:

        type_flags = (
            bool(entry.is_file),
            bool(entry.is_directory),
            bool(entry.is_symlink),
            bool(entry.is_hardlink),
        )

        type_count = sum(type_flags)

        # Nothing identifies the entry.
        if type_count == 0:
            raise UnsupportedEntryError(
                (
                    f"Archive entry '{entry.name}' has an "
                    f"unsupported entry type."
                ),
                phase=PHASE_SECURITY,
                check="unsupported_entry_validation",
                code="UNSUPPORTED_ARCHIVE_ENTRY",
                details={
                    "entry": entry.name,
                    "metadata": entry.metadata,
                },
            )

        # More than one type at the same time means our metadata
        # is inconsistent or the entry is ambiguous.
        if type_count > 1:
            raise UnsupportedEntryError(
                (
                    f"Archive entry '{entry.name}' has "
                    f"inconsistent entry-type metadata."
                ),
                phase=PHASE_SECURITY,
                check="unsupported_entry_validation",
                code="AMBIGUOUS_ARCHIVE_ENTRY_TYPE",
                details={
                    "entry": entry.name,
                    "is_file": entry.is_file,
                    "is_directory": entry.is_directory,
                    "is_symlink": entry.is_symlink,
                    "is_hardlink": entry.is_hardlink,
                },
            )


def validate_archive_entries(
    context: ArchiveValidationContext,
) -> None:
    """
    Run all general archive-entry validations.

    Link policy itself is handled separately by links.py.
    """

    validate_empty_archive(context)
    validate_duplicate_entries(context)
    validate_supported_entries(context)