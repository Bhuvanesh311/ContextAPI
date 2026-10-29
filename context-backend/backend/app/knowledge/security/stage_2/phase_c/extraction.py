import tarfile
import zipfile
from pathlib import Path

from app.knowledge.security.stage_2.constants import (
    MAX_SINGLE_ENTRY_SIZE,
    MAX_TOTAL_EXTRACTED_SIZE,
    PHASE_EXTRACTION,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.phase_c.ignore import (
    is_ignored_member,
)
from app.knowledge.security.stage_2.exceptions import (
    ArchiveExtractionError,
    ArchiveValidationError,
    EntrySizeExceededError,
    ExtractedSizeExceededError,
    PathTraversalError,
)


CHUNK_SIZE = 1024 * 1024  # 1 MiB



# Destination containment



def _safe_destination(
    workspace: Path,
    member_name: str,
) -> Path:


    workspace = workspace.resolve()

    normalized_name = member_name.replace("\\", "/")

    destination = (
        workspace / normalized_name
    ).resolve()

    try:
        destination.relative_to(workspace)

    except ValueError as exc:
        raise PathTraversalError(
            (
                f"Archive member '{member_name}' resolves "
                f"outside the controlled extraction workspace."
            ),
            phase=PHASE_EXTRACTION,
            check="extraction_path_containment",
            code="EXTRACTION_PATH_ESCAPE",
            details={
                "entry": member_name,
                "workspace": str(workspace),
                "destination": str(destination),
            },
        ) from exc

    return destination



# ZIP extraction



def _extract_zip(
    context: ArchiveValidationContext,
    workspace: Path,
) -> list[Path]:


    extracted_paths: list[Path] = []

    total_written = 0

    workspace = workspace.resolve()

    with zipfile.ZipFile(
        context.file_path,
        "r",
    ) as archive:

        for info in archive.infolist():

            destination = _safe_destination(
                workspace,
                info.filename,
            )

        
            # Directory
        

            if info.is_dir():

                destination.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                continue


            # VCS data, caches, build output

            if is_ignored_member(info.filename):

                context.skipped_entries.append(
                    info.filename
                )

                continue

        
            # Prepare parent directory
        

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            entry_written = 0

            # True only after THIS extraction successfully
            # creates the destination file.
            created_destination = False

            try:

                with archive.open(
                    info,
                    "r",
                ) as source:

                    # Exclusive creation prevents overwriting
                    # anything already present in the workspace.
                    with destination.open(
                        "xb"
                    ) as target:

                        created_destination = True

                        while True:

                            chunk = source.read(
                                CHUNK_SIZE
                            )

                            if not chunk:
                                break

                            chunk_size = len(chunk)

                            entry_written += chunk_size
                            total_written += chunk_size

                            
                            # Actual per-entry size
                            

                            if (
                                entry_written
                                > MAX_SINGLE_ENTRY_SIZE
                            ):
                                raise EntrySizeExceededError(
                                    (
                                        f"Archive entry "
                                        f"'{info.filename}' exceeded "
                                        f"the maximum extracted size."
                                    ),
                                    phase=PHASE_EXTRACTION,
                                    check=(
                                        "runtime_entry_size_validation"
                                    ),
                                    code=(
                                        "RUNTIME_ENTRY_SIZE_EXCEEDED"
                                    ),
                                    details={
                                        "entry": info.filename,
                                        "bytes_written": (
                                            entry_written
                                        ),
                                        "maximum": (
                                            MAX_SINGLE_ENTRY_SIZE
                                        ),
                                    },
                                )

                            
                            # Actual total extracted size
                            

                            if (
                                total_written
                                > MAX_TOTAL_EXTRACTED_SIZE
                            ):
                                raise ExtractedSizeExceededError(
                                    (
                                        f"Archive "
                                        f"'{context.original_filename}' "
                                        f"exceeded the maximum total "
                                        f"extracted size."
                                    ),
                                    phase=PHASE_EXTRACTION,
                                    check=(
                                        "runtime_total_size_validation"
                                    ),
                                    code=(
                                        "RUNTIME_TOTAL_SIZE_EXCEEDED"
                                    ),
                                    details={
                                        "bytes_written": (
                                            total_written
                                        ),
                                        "maximum": (
                                            MAX_TOTAL_EXTRACTED_SIZE
                                        ),
                                    },
                                )

                            target.write(chunk)

            except Exception:

                if created_destination:
                    destination.unlink(
                        missing_ok=True
                    )

                raise

            extracted_paths.append(
                destination
            )

    return extracted_paths



# TAR extraction



def _extract_tar(
    context: ArchiveValidationContext,
    workspace: Path,
) -> list[Path]:

    extracted_paths: list[Path] = []

    total_written = 0

    workspace = workspace.resolve()

    # Open TAR

    try:
        archive = tarfile.open(
            context.file_path,
            mode="r:",
        )

    except (tarfile.TarError, OSError) as exc:
        raise ArchiveExtractionError(
            (
                f"Unable to open TAR archive "
                f"'{context.original_filename}'."
            ),
            phase=PHASE_EXTRACTION,
            check="secure_extraction",
            code="TAR_OPEN_FAILED",
            details={
                "archive": context.original_filename,
            },
        ) from exc

    with archive:

        for member in archive:

        
            # Resolve safe destination
        

            destination = _safe_destination(
                workspace,
                member.name,
            )

        
            # Directory
        

            if member.isdir():

                destination.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                continue

        
            # Symbolic links
        

            if member.issym():

                raise ArchiveExtractionError(
                    (
                        f"Symbolic link '{member.name}' "
                        f"is not allowed during TAR extraction."
                    ),
                    phase=PHASE_EXTRACTION,
                    check="secure_extraction",
                    code="TAR_SYMLINK_NOT_ALLOWED",
                    details={
                        "entry": member.name,
                    },
                )

        
            # Hard links
        

            if member.islnk():

                raise ArchiveExtractionError(
                    (
                        f"Hard link '{member.name}' "
                        f"is not allowed during TAR extraction."
                    ),
                    phase=PHASE_EXTRACTION,
                    check="secure_extraction",
                    code="TAR_HARDLINK_NOT_ALLOWED",
                    details={
                        "entry": member.name,
                    },
                )

        
          
            if not member.isfile():

                raise ArchiveExtractionError(
                    (
                        f"Unsupported TAR member type for "
                        f"'{member.name}'."
                    ),
                    phase=PHASE_EXTRACTION,
                    check="secure_extraction",
                    code="TAR_SPECIAL_ENTRY_NOT_ALLOWED",
                    details={
                        "entry": member.name,
                        "type": repr(member.type),
                    },
                )


            # VCS data, caches, build output

            if is_ignored_member(member.name):

                context.skipped_entries.append(
                    member.name
                )

                continue

        
            # Declared per-entry size
        

            if member.size > MAX_SINGLE_ENTRY_SIZE:

                raise EntrySizeExceededError(
                    (
                        f"Archive entry '{member.name}' exceeded "
                        f"the maximum allowed size."
                    ),
                    phase=PHASE_EXTRACTION,
                    check="runtime_entry_size_validation",
                    code="RUNTIME_ENTRY_SIZE_EXCEEDED",
                    details={
                        "entry": member.name,
                        "declared_size": member.size,
                        "maximum": MAX_SINGLE_ENTRY_SIZE,
                    },
                )

        
            # Prepare parent directory
        

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            entry_written = 0

            created_destination = False

            try:

            
                # Open member stream
            

                source = archive.extractfile(
                    member
                )

                if source is None:

                    raise ArchiveExtractionError(
                        (
                            f"Unable to read TAR entry "
                            f"'{member.name}'."
                        ),
                        phase=PHASE_EXTRACTION,
                        check="secure_extraction",
                        code="TAR_ENTRY_READ_FAILED",
                        details={
                            "entry": member.name,
                        },
                    )

                with source:

                    # Exclusive creation.
                    #
                    # Never overwrite an existing file.
                    with destination.open(
                        "xb"
                    ) as target:

                        created_destination = True

                        while True:

                            chunk = source.read(
                                CHUNK_SIZE
                            )

                            if not chunk:
                                break

                            chunk_size = len(chunk)

                            entry_written += chunk_size
                            total_written += chunk_size

                            
                            # Actual per-entry size
                            

                            if (
                                entry_written
                                > MAX_SINGLE_ENTRY_SIZE
                            ):

                                raise EntrySizeExceededError(
                                    (
                                        f"Archive entry "
                                        f"'{member.name}' exceeded "
                                        f"the maximum extracted size."
                                    ),
                                    phase=PHASE_EXTRACTION,
                                    check=(
                                        "runtime_entry_size_validation"
                                    ),
                                    code=(
                                        "RUNTIME_ENTRY_SIZE_EXCEEDED"
                                    ),
                                    details={
                                        "entry": member.name,
                                        "bytes_written": (
                                            entry_written
                                        ),
                                        "maximum": (
                                            MAX_SINGLE_ENTRY_SIZE
                                        ),
                                    },
                                )

                            
                            # Actual total extracted size
                            

                            if (
                                total_written
                                > MAX_TOTAL_EXTRACTED_SIZE
                            ):

                                raise ExtractedSizeExceededError(
                                    (
                                        f"Archive "
                                        f"'{context.original_filename}' "
                                        f"exceeded the maximum total "
                                        f"extracted size."
                                    ),
                                    phase=PHASE_EXTRACTION,
                                    check=(
                                        "runtime_total_size_validation"
                                    ),
                                    code=(
                                        "RUNTIME_TOTAL_SIZE_EXCEEDED"
                                    ),
                                    details={
                                        "bytes_written": (
                                            total_written
                                        ),
                                        "maximum": (
                                            MAX_TOTAL_EXTRACTED_SIZE
                                        ),
                                    },
                                )

                            target.write(
                                chunk
                            )

            except Exception:

            
                # Cleanup only files created by this extraction
            

                if created_destination:

                    destination.unlink(
                        missing_ok=True
                    )

                raise

            extracted_paths.append(
                destination
            )

    return extracted_paths



# Public extraction API



def extract_archive_securely(
    context: ArchiveValidationContext,
) -> list[Path]:
    """
    Perform controlled archive extraction after Phase A and Phase B.

    Supported archive formats:

        ZIP
        TAR

    This function is the Phase C extraction dispatcher.

    Format-specific extraction logic remains isolated in dedicated
    private functions so additional archive formats can later be
    introduced without changing the public Phase C interface.
    """

    context.current_phase = PHASE_EXTRACTION
    context.current_check = "secure_extraction"

    workspace = context.extraction_workspace

    # Workspace must exist

    if workspace is None:

        raise ArchiveExtractionError(
            (
                "Extraction workspace has not "
                "been created."
            ),
            phase=PHASE_EXTRACTION,
            check="secure_extraction",
            code="EXTRACTION_WORKSPACE_MISSING",
        )

    workspace = Path(
        workspace
    ).resolve()

    # Workspace existence

    if not workspace.exists():

        raise ArchiveExtractionError(
            (
                "Extraction workspace does not exist."
            ),
            phase=PHASE_EXTRACTION,
            check="secure_extraction",
            code="EXTRACTION_WORKSPACE_NOT_FOUND",
            details={
                "workspace": str(workspace),
            },
        )

    # Workspace type

    if not workspace.is_dir():

        raise ArchiveExtractionError(
            (
                "Extraction workspace is not "
                "a directory."
            ),
            phase=PHASE_EXTRACTION,
            check="secure_extraction",
            code="INVALID_EXTRACTION_WORKSPACE",
            details={
                "workspace": str(workspace),
            },
        )

    try:

   
        # Normalize archive type
   

        archive_type = (
            context.archive_type.value
            if hasattr(
                context.archive_type,
                "value",
            )
            else str(
                context.archive_type
            )
        )

        archive_type = (
            archive_type
            .strip()
            .lower()
        )

   
        # Dispatch extractor
   

        if archive_type == "zip":

            paths = _extract_zip(
                context,
                workspace,
            )

        elif archive_type == "tar":

            paths = _extract_tar(
                context,
                workspace,
            )

        else:

            raise ArchiveExtractionError(
                (
                    f"Controlled extraction for archive type "
                    f"'{archive_type}' is not implemented."
                ),
                phase=PHASE_EXTRACTION,
                check="secure_extraction",
                code="EXTRACTION_FORMAT_NOT_IMPLEMENTED",
                details={
                    "archive_type": archive_type,
                },
            )

   
        # Commit result to context
   
        #
        # Do not update extracted_paths until the entire
        # extraction operation succeeds.
   

        context.extracted_paths = paths

        return paths

    # Security / validation rejection

    except ArchiveValidationError:
        raise

    # Known extraction operational error

    except ArchiveExtractionError:
        raise

    # Unexpected operational failure

    except Exception as exc:

        raise ArchiveExtractionError(
            (
                f"Controlled extraction failed for "
                f"'{context.original_filename}'."
            ),
            phase=PHASE_EXTRACTION,
            check="secure_extraction",
            code="ARCHIVE_EXTRACTION_FAILED",
            details={
                "document_id": context.document_id,
                "archive": context.original_filename,
            },
        ) from exc