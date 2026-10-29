import ntpath
import posixpath
import re

from app.knowledge.security.stage_2.constants import (
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    AbsolutePathError,
    PathTraversalError,
)


WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _normalize_archive_path(name: str) -> str:
    """
    ZIP/TAR member names should be treated as archive paths,
    not as paths belonging to the host operating system.

    Convert backslashes as well because hostile archives may
    deliberately use Windows separators.
    """
    return name.replace("\\", "/")


def _is_absolute_archive_path(name: str) -> bool:
    normalized = _normalize_archive_path(name)

    # POSIX absolute path
    if normalized.startswith("/"):
        return True

    # Windows drive path: C:/..., C:\...
    if WINDOWS_DRIVE_RE.match(name):
        return True

    # UNC path: \\server\share or //server/share
    if name.startswith("\\\\") or normalized.startswith("//"):
        return True

    # ntpath catches additional Windows absolute-path forms.
    if ntpath.isabs(name):
        return True

    return False


def _contains_traversal(name: str) -> bool:
    normalized = _normalize_archive_path(name)

    parts = normalized.split("/")

    depth = 0

    for part in parts:

        if part in {"", "."}:
            continue

        if part == "..":
            if depth == 0:
                return True

            depth -= 1
            continue

        depth += 1

    return False


def validate_absolute_paths(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "absolute_path_validation"

    for entry in context.entries:

        if _is_absolute_archive_path(entry.name):
            raise AbsolutePathError(
                (
                    f"Archive entry '{entry.name}' contains "
                    f"an absolute path."
                ),
                phase=PHASE_SECURITY,
                check="absolute_path_validation",
                code="ABSOLUTE_ARCHIVE_PATH",
                details={
                    "entry": entry.name,
                },
            )


def validate_path_traversal(
    context: ArchiveValidationContext,
) -> None:

    context.current_phase = PHASE_SECURITY
    context.current_check = "path_traversal_validation"

    for entry in context.entries:

        if _contains_traversal(entry.name):
            raise PathTraversalError(
                (
                    f"Archive entry '{entry.name}' attempts "
                    f"path traversal outside the extraction root."
                ),
                phase=PHASE_SECURITY,
                check="path_traversal_validation",
                code="ARCHIVE_PATH_TRAVERSAL",
                details={
                    "entry": entry.name,
                },
            )


def validate_archive_paths(
    context: ArchiveValidationContext,
) -> None:
    """
    Validate all member paths before extraction.

    IMPORTANT:
    Phase C must still perform destination containment checks
    immediately before writing each extracted file.
    """

    validate_absolute_paths(context)
    validate_path_traversal(context)