import re

from app.knowledge.security.stage_2.constants import (
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    UnsafeArchiveFilenameError,
)



# Filename Policy


MAX_ENTRY_PATH_LENGTH = 1024
MAX_PATH_COMPONENT_LENGTH = 255


# ASCII control characters:
#
# 0x00 - 0x1F
# 0x7F
#
CONTROL_CHARACTER_RE = re.compile(
    r"[\x00-\x1f\x7f]"
)


# Windows reserved device names.
#
# These remain reserved even when an extension is present:
#
# CON.txt
# NUL.json
# COM1.log
#
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",

    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",

    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def _normalize_archive_name(name: str,) -> str:
    """
    Normalize archive separators for validation.

    This does NOT resolve '..'.

    Path traversal belongs to paths.py.
    """

    return name.replace("\\", "/")


def _is_windows_reserved_name(component: str,) -> bool:
    """
    Detect Windows reserved device names.

    Examples:

        CON
        CON.txt
        nul.json
        COM1.log
    """

    cleaned = component.rstrip(" .")

    base_name = cleaned.split(".", 1)[0]

    return base_name.upper() in WINDOWS_RESERVED_NAMES


def _validate_component(component: str,*,full_name: str,) -> None:
    """
    Validate one path component inside an archive entry.
    """

    # --------------------------------------------------------
    # Component length
    # --------------------------------------------------------

    if len(component) > MAX_PATH_COMPONENT_LENGTH:
        raise UnsafeArchiveFilenameError(
            (
                f"Archive entry '{full_name}' contains "
                f"a path component longer than "
                f"{MAX_PATH_COMPONENT_LENGTH} characters."
            ),
            phase=PHASE_SECURITY,
            check="archive_filename_validation",
            code="ARCHIVE_FILENAME_COMPONENT_TOO_LONG",
            details={
                "entry": full_name,
                "component": component,
                "component_length": len(component),
                "maximum": MAX_PATH_COMPONENT_LENGTH,
            },
        )

    # --------------------------------------------------------
    # Control characters / NUL
    # --------------------------------------------------------

    if CONTROL_CHARACTER_RE.search(component):
        raise UnsafeArchiveFilenameError(
            (
                f"Archive entry '{full_name}' contains "
                f"control characters."
            ),
            phase=PHASE_SECURITY,
            check="archive_filename_validation",
            code="ARCHIVE_FILENAME_CONTROL_CHARACTER",
            details={
                "entry": full_name,
                "component": repr(component),
            },
        )

    # --------------------------------------------------------
    # Windows reserved names
    # --------------------------------------------------------

    if _is_windows_reserved_name(component):
        raise UnsafeArchiveFilenameError(
            (
                f"Archive entry '{full_name}' uses "
                f"reserved filename '{component}'."
            ),
            phase=PHASE_SECURITY,
            check="archive_filename_validation",
            code="RESERVED_ARCHIVE_FILENAME",
            details={
                "entry": full_name,
                "component": component,
            },
        )

    # --------------------------------------------------------
    # Trailing period / whitespace
    # --------------------------------------------------------

    if component.endswith((" ", ".")):
        raise UnsafeArchiveFilenameError(
            (
                f"Archive entry '{full_name}' contains "
                f"a path component ending with a space "
                f"or period."
            ),
            phase=PHASE_SECURITY,
            check="archive_filename_validation",
            code="UNSAFE_FILENAME_SUFFIX",
            details={
                "entry": full_name,
                "component": component,
            },
        )


def validate_archive_filenames(context: ArchiveValidationContext,) -> None:
    """
    Validate archive member names.

    This validator handles filename/path-component policy.

    It does NOT handle:
        ../ traversal
        absolute paths
        drive paths
        UNC paths

    Those belong to paths.py.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "archive_filename_validation"

    for entry in context.entries:

        name = entry.name

        # ----------------------------------------------------
        # Type
        # ----------------------------------------------------

        if not isinstance(name, str):
            raise UnsafeArchiveFilenameError(
                "Archive entry name is not a string.",
                phase=PHASE_SECURITY,
                check="archive_filename_validation",
                code="INVALID_ARCHIVE_FILENAME_TYPE",
                details={
                    "entry_type": type(name).__name__,
                },
            )

        # ----------------------------------------------------
        # Empty name
        # ----------------------------------------------------

        if not name:
            raise UnsafeArchiveFilenameError(
                "Archive contains an empty entry name.",
                phase=PHASE_SECURITY,
                check="archive_filename_validation",
                code="EMPTY_ARCHIVE_FILENAME",
            )

        normalized = _normalize_archive_name(
            name
        )

        # ----------------------------------------------------
        # Entire path length
        # ----------------------------------------------------

        if len(normalized) > MAX_ENTRY_PATH_LENGTH:
            raise UnsafeArchiveFilenameError(
                (
                    f"Archive entry '{name}' exceeds "
                    f"the maximum path length of "
                    f"{MAX_ENTRY_PATH_LENGTH} characters."
                ),
                phase=PHASE_SECURITY,
                check="archive_filename_validation",
                code="ARCHIVE_PATH_TOO_LONG",
                details={
                    "entry": name,
                    "length": len(normalized),
                    "maximum": MAX_ENTRY_PATH_LENGTH,
                },
            )

        components = normalized.split("/")

        # ----------------------------------------------------
        # Directory trailing slash
        # ----------------------------------------------------
        #
        # "folder/" becomes:
        #
        # ["folder", ""]
        #
        # That final empty component is legitimate for a
        # directory entry.
        # ----------------------------------------------------

        if (
            entry.is_directory
            and components
            and components[-1] == ""
        ):
            components = components[:-1]

        # ----------------------------------------------------
        # Components
        # ----------------------------------------------------

        for component in components:

            # Internal empty components:
            #
            # folder//file.txt
            #
            # are rejected.
            if component == "":
                raise UnsafeArchiveFilenameError(
                    (
                        f"Archive entry '{name}' contains "
                        f"an empty path component."
                    ),
                    phase=PHASE_SECURITY,
                    check="archive_filename_validation",
                    code="EMPTY_PATH_COMPONENT",
                    details={
                        "entry": name,
                    },
                )

            # "." and ".." are path semantics.
            #
            # paths.py owns traversal/path safety so we don't
            # duplicate that responsibility here.
            if component in {".", ".."}:
                continue

            _validate_component(
                component,
                full_name=name,
            )