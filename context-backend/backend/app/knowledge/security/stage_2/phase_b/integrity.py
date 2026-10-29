import tarfile
import zipfile

from app.knowledge.security.stage_2.constants import (
    ArchiveType,
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveIntegrityError,
    UnsupportedArchiveError,
)


def validate_archive_integrity(
    context: ArchiveValidationContext,
) -> None:
    """
    Validate that the archive can be read consistently.

    ZIP:
        Uses ZipFile.testzip(), which reads archive members and
        checks their CRC values.

    TAR / TAR.GZ:
        Iterates members and reads regular-file contents so
        truncation/read failures are surfaced before extraction.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "archive_integrity_validation"

    archive_type = context.archive_type

    if archive_type is None:
        raise ArchiveIntegrityError(
            "Archive type is unavailable.",
            phase=PHASE_SECURITY,
            check="archive_integrity_validation",
            code="ARCHIVE_TYPE_MISSING",
        )

    try:
        if archive_type == ArchiveType.ZIP:
            with zipfile.ZipFile(
                context.file_path,
                "r",
            ) as archive:

                bad_entry = archive.testzip()

                if bad_entry is not None:
                    context.integrity_valid = False

                    raise ArchiveIntegrityError(
                        (
                            f"Archive integrity check failed for "
                            f"entry '{bad_entry}' in "
                            f"'{context.original_filename}'."
                        ),
                        phase=PHASE_SECURITY,
                        check="archive_integrity_validation",
                        code="ZIP_CRC_FAILURE",
                        details={
                            "entry": bad_entry,
                        },
                    )

        elif archive_type in {
            ArchiveType.TAR,
            ArchiveType.TAR_GZ,
        }:
            with tarfile.open(
                context.file_path,
                mode="r:*",
            ) as archive:

                for member in archive:

                    if not member.isfile():
                        continue

                    source = archive.extractfile(member)

                    if source is None:
                        context.integrity_valid = False

                        raise ArchiveIntegrityError(
                            (
                                f"Unable to read TAR entry "
                                f"'{member.name}'."
                            ),
                            phase=PHASE_SECURITY,
                            check="archive_integrity_validation",
                            code="TAR_ENTRY_UNREADABLE",
                            details={
                                "entry": member.name,
                            },
                        )

                    with source:
                        while source.read(1024 * 1024):
                            pass

        else:
            raise UnsupportedArchiveError(
                (
                    f"Integrity validator for archive type "
                    f"'{archive_type.value}' is not implemented."
                ),
                phase=PHASE_SECURITY,
                check="archive_integrity_validation",
                code="INTEGRITY_HANDLER_NOT_IMPLEMENTED",
            )

    except ArchiveIntegrityError:
        raise

    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        EOFError,
        OSError,
    ) as exc:

        context.integrity_valid = False

        raise ArchiveIntegrityError(
            (
                f"Archive '{context.original_filename}' "
                f"failed integrity validation."
            ),
            phase=PHASE_SECURITY,
            check="archive_integrity_validation",
            code="ARCHIVE_INTEGRITY_FAILURE",
            details={
                "exception_type": type(exc).__name__,
            },
        ) from exc

    context.integrity_valid = True