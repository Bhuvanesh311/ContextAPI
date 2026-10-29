import stat
import tarfile
import zipfile

from app.knowledge.security.stage_2.constants import (
    ArchiveType,
    PHASE_IDENTITY_METADATA,
)
from app.knowledge.security.stage_2.context import (
    ArchiveEntry,
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveMetadataError,
)


def _compression_ratio(
    compressed: int,
    uncompressed: int,
) -> float:
    if uncompressed <= 0:
        return 0.0

    if compressed <= 0:
        return float("inf")

    return uncompressed / compressed


def _collect_zip_metadata(
    context: ArchiveValidationContext,
) -> None:

    with zipfile.ZipFile(context.file_path, "r") as archive:
        for info in archive.infolist():

            unix_mode = (info.external_attr >> 16) & 0xFFFF

            is_symlink = (
                unix_mode != 0
                and stat.S_ISLNK(unix_mode)
            )

            is_directory = info.is_dir()

            is_encrypted = bool(info.flag_bits & 0x1)

            entry = ArchiveEntry(
                name=info.filename,
                compressed_size=info.compress_size,
                uncompressed_size=info.file_size,
                compression_method=str(info.compress_type),
                is_directory=is_directory,
                is_file=(not is_directory and not is_symlink),
                is_symlink=is_symlink,
                is_hardlink=False,
                is_encrypted=is_encrypted,
                metadata={
                    "crc": info.CRC,
                    "flag_bits": info.flag_bits,
                    "external_attr": info.external_attr,
                },
            )

            context.add_entry(entry)


def _collect_tar_metadata(
    context: ArchiveValidationContext,
) -> None:

    with tarfile.open(context.file_path, mode="r:*") as archive:
        for member in archive.getmembers():

            is_directory = member.isdir()
            is_file = member.isfile()
            is_symlink = member.issym()
            is_hardlink = member.islnk()

            entry = ArchiveEntry(
                name=member.name,
                compressed_size=0,
                uncompressed_size=member.size,
                compression_method=(
                    context.archive_type.value
                    if context.archive_type
                    else None
                ),
                is_directory=is_directory,
                is_file=is_file,
                is_symlink=is_symlink,
                is_hardlink=is_hardlink,
                is_encrypted=False,
                metadata={
                    "mode": member.mode,
                    "uid": member.uid,
                    "gid": member.gid,
                    "linkname": member.linkname,
                    "type": repr(member.type),
                },
            )

            context.add_entry(entry)


def collect_archive_metadata(
    context: ArchiveValidationContext,
) -> None:
    """
    Read archive metadata without extracting entries and
    normalize it into ArchiveEntry objects.
    """

    context.current_phase = PHASE_IDENTITY_METADATA
    context.current_check = "archive_metadata_collection"

    if context.archive_type is None:
        raise ArchiveMetadataError(
            "Archive type is unavailable.",
            phase=PHASE_IDENTITY_METADATA,
            check="archive_metadata_collection",
            code="ARCHIVE_TYPE_MISSING",
        )

    # Prevent accidental double collection.
    context.entries.clear()
    context.compression_methods.clear()

    try:
        if context.archive_type == ArchiveType.ZIP:
            _collect_zip_metadata(context)

        elif context.archive_type in {
            ArchiveType.TAR,
            ArchiveType.TAR_GZ,
        }:
            _collect_tar_metadata(context)

        else:
            raise ArchiveMetadataError(
                (
                    f"Metadata collector for "
                    f"'{context.archive_type.value}' "
                    f"is not implemented."
                ),
                phase=PHASE_IDENTITY_METADATA,
                check="archive_metadata_collection",
                code="METADATA_HANDLER_NOT_IMPLEMENTED",
            )

    except (
        zipfile.BadZipFile,
        tarfile.TarError,
        OSError,
    ) as exc:
        raise ArchiveMetadataError(
            (
                f"Unable to collect metadata from "
                f"'{context.original_filename}'."
            ),
            phase=PHASE_IDENTITY_METADATA,
            check="archive_metadata_collection",
            code="ARCHIVE_METADATA_READ_FAILED",
        ) from exc

    context.entry_count = len(context.entries)

    context.compressed_size = sum(
        entry.compressed_size
        for entry in context.entries
        if entry.is_file
    )

    context.estimated_extracted_size = sum(
        entry.uncompressed_size
        for entry in context.entries
        if entry.is_file
    )

    context.compression_methods = {
        entry.compression_method
        for entry in context.entries
        if entry.compression_method is not None
    }

    context.encrypted = any(
        entry.is_encrypted
        for entry in context.entries
    )

    context.password_protected = context.encrypted

    context.contains_symlinks = any(
        entry.is_symlink
        for entry in context.entries
    )

    context.contains_hardlinks = any(
        entry.is_hardlink
        for entry in context.entries
    )

    if context.archive_type == ArchiveType.ZIP:
        context.compression_ratio = _compression_ratio(
            context.compressed_size,
            context.estimated_extracted_size,
        )
    else:
        # TAR member metadata does not provide per-entry
        # compressed sizes for compressed TAR streams.
        #
        # Phase B can compare the archive's physical size
        # against total member size instead.
        context.compression_ratio = None