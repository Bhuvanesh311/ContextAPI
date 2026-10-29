from app.knowledge.security.stage_2.constants import (
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    HardLinkError,
    SymbolicLinkError,
)


def validate_symbolic_links(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "symbolic_link_validation"

    symbolic_links = [
        entry.name
        for entry in context.entries
        if entry.is_symlink
    ]

    context.contains_symlinks = bool(symbolic_links)

    if symbolic_links:
        raise SymbolicLinkError(
            (
                f"Archive '{context.original_filename}' "
                f"contains symbolic links."
            ),
            phase=PHASE_SECURITY,
            check="symbolic_link_validation",
            code="SYMBOLIC_LINK_NOT_ALLOWED",
            details={
                "count": len(symbolic_links),
                "entries": symbolic_links[:50],
            },
        )


def validate_hard_links(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "hard_link_validation"

    hard_links = [
        entry.name
        for entry in context.entries
        if entry.is_hardlink
    ]

    context.contains_hardlinks = bool(hard_links)

    if hard_links:
        raise HardLinkError(
            (
                f"Archive '{context.original_filename}' "
                f"contains hard links."
            ),
            phase=PHASE_SECURITY,
            check="hard_link_validation",
            code="HARD_LINK_NOT_ALLOWED",
            details={
                "count": len(hard_links),
                "entries": hard_links[:50],
            },
        )


def validate_archive_links(
    context: ArchiveValidationContext,
) -> None:

    validate_symbolic_links(context)
    validate_hard_links(context)