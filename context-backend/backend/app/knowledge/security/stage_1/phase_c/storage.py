import hashlib
import os

from app.knowledge.security.stage_1.constants import (
    HASH_ALGORITHM,
    HASH_CHUNK_SIZE,
    STORAGE_HASH_MISMATCH,
    STORAGE_MISSING,
    STORAGE_SIZE_MISMATCH,
    STORAGE_UNREADABLE,
    STORAGE_VERIFIED,
)
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import (
    StorageFileMissingError,
    StorageHashMismatchError,
    StorageSizeMismatchError,
    StorageUnreadableError,
    StorageVerificationError,
)


def verify_storage(context: ValidationContext) -> None:
    
    file_path = context.file_path

    
    # File existence
    

    if not file_path.exists():
        context.storage_status = STORAGE_MISSING
        context.storage_exists = False

        raise StorageFileMissingError(
            f"Stored file '{context.original_filename}' "
            f"no longer exists.",
            phase="security",
            check="storage_verification",
            code="STORAGE_FILE_MISSING",
        )

    context.storage_exists = True

    
    # Regular file
    

    if not file_path.is_file():
        context.storage_status = STORAGE_UNREADABLE
        context.storage_readable = False

        raise StorageUnreadableError(
            f"Stored path for '{context.original_filename}' "
            f"is not a regular file.",
            phase="security",
            check="storage_verification",
            code="STORAGE_NOT_REGULAR_FILE",
        )

    
    # Readability
    

    if not os.access(file_path, os.R_OK):
        context.storage_status = STORAGE_UNREADABLE
        context.storage_readable = False

        raise StorageUnreadableError(
            f"Stored file '{context.original_filename}' "
            f"is not readable.",
            phase="security",
            check="storage_verification",
            code="STORAGE_UNREADABLE",
        )

    context.storage_readable = True

    
    # Expected values
    

    if context.file_size is None:
        raise StorageVerificationError(
            f"Expected file size is unavailable for "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="EXPECTED_SIZE_UNAVAILABLE",
        )

    if not context.sha256:
        raise StorageVerificationError(
            f"Expected SHA-256 hash is unavailable for "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="EXPECTED_HASH_UNAVAILABLE",
        )

    
    # Size verification
    

    try:
        current_size = file_path.stat().st_size

    except OSError as exc:
        context.storage_status = STORAGE_UNREADABLE
        context.storage_readable = False

        raise StorageUnreadableError(
            f"Unable to inspect stored file "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="STORAGE_STAT_FAILED",
        ) from exc

    if current_size != context.file_size:
        context.storage_status = STORAGE_SIZE_MISMATCH
        context.storage_size_match = False

        raise StorageSizeMismatchError(
            f"Stored file size changed for "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="STORAGE_SIZE_MISMATCH",
        )

    context.storage_size_match = True

    
    # Hash verification
    

    try:
        hasher = hashlib.new(HASH_ALGORITHM)

        with file_path.open("rb") as file:
            while chunk := file.read(HASH_CHUNK_SIZE):
                hasher.update(chunk)

        current_hash = hasher.hexdigest()

    except (OSError, ValueError) as exc:
        context.storage_status = STORAGE_UNREADABLE

        raise StorageUnreadableError(
            f"Unable to verify stored file hash for "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="STORAGE_HASH_READ_FAILED",
        ) from exc

    if current_hash != context.sha256:
        context.storage_status = STORAGE_HASH_MISMATCH
        context.storage_hash_match = False

        raise StorageHashMismatchError(
            f"Stored file hash changed for "
            f"'{context.original_filename}'.",
            phase="security",
            check="storage_verification",
            code="STORAGE_HASH_MISMATCH",
        )

    context.storage_hash_match = True

    
    # Verification successful
    

    context.storage_status = STORAGE_VERIFIED