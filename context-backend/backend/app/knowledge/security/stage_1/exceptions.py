class StageOneValidationError(Exception):
    """
    Base exception for all Stage 1 Universal Validation failures.
    """

    def __init__(
        self,
        message: str,
        *,
        phase: str | None = None,
        check: str | None = None,
        code: str | None = None,
    ):
        super().__init__(message)

        self.message = message
        self.phase = phase
        self.check = check
        self.code = code

    def __str__(self) -> str:
        return self.message


# Phase A - Identity & Metadata


class IdentityValidationError(StageOneValidationError):
    """Base exception for identity validation failures."""


class FileNotFoundValidationError(IdentityValidationError):
    """Raised when the uploaded file cannot be found."""


class FileMetadataError(IdentityValidationError):
    """Raised when file metadata cannot be collected or validated."""


# Phase B - Integrity & Trust


class IntegrityValidationError(StageOneValidationError):
    """Base exception for integrity and trust failures."""


class MimeDetectionError(IntegrityValidationError):
    """Raised when MIME detection fails."""


class UnsupportedDetectedMimeError(IntegrityValidationError):
    """Raised when the detected MIME type is not supported."""


class SignatureValidationError(IntegrityValidationError):
    """Raised when the file signature cannot be validated."""


class MimeSignatureMismatchError(IntegrityValidationError):
    """Raised when MIME type and file signature are inconsistent."""


class HashGenerationError(IntegrityValidationError):
    """Raised when the file hash cannot be generated."""


class DuplicateFileError(IntegrityValidationError):
    """Raised when the file content already exists."""


# Phase C - Security


class SecurityValidationError(StageOneValidationError):
    """Base exception for Stage 1 security failures."""


class ContentDetectionError(SecurityValidationError):
    """Raised when binary/text classification fails."""


class EncodingDetectionError(SecurityValidationError):
    """Raised when text encoding cannot be reliably determined."""


class EntropyAnalysisError(SecurityValidationError):
    """Raised when entropy analysis cannot be performed."""


class MalwareScanError(SecurityValidationError):
    """
    Raised when the malware scanner itself fails or cannot
    determine whether the file is safe.
    """


class MalwareDetectedError(SecurityValidationError):
    """Raised when malware is detected in the file."""


class StorageVerificationError(SecurityValidationError):
    """Raised when stored file verification fails."""


class StorageFileMissingError(StorageVerificationError):
    """Raised when the expected stored file does not exist."""


class StorageSizeMismatchError(StorageVerificationError):
    """Raised when the stored file size differs from the expected size."""


class StorageHashMismatchError(StorageVerificationError):
    """Raised when the stored file hash differs from the expected hash."""


class StorageUnreadableError(StorageVerificationError):
    """Raised when the stored file cannot be read."""


# Pipeline


class StageOnePipelineError(StageOneValidationError):
    """
    Raised when Stage 1 cannot complete because of an
    orchestration/internal pipeline failure.
    """