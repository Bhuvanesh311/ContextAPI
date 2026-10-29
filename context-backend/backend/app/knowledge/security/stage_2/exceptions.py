from typing import Any



# Base Stage 2 Exception



class StageTwoError(Exception):
    """
    Base exception for every Stage 2 failure.
    """

    def __init__(
        self,
        message: str,
        *,
        phase: str | None = None,
        check: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:

        super().__init__(message)

        self.message = message
        self.phase = phase
        self.check = check
        self.code = code
        self.details = details or {}



# Validation Rejection



class ArchiveValidationError(StageTwoError):
    """
    The archive itself violated Stage 2 security policy.

    These failures mean the archive should be rejected.
    """



# Phase A



class ArchiveTypeDetectionError(
    ArchiveValidationError
):
    pass


class UnsupportedArchiveError(
    ArchiveValidationError
):
    pass


class ArchiveFormatError(
    ArchiveValidationError
):
    pass


class ArchiveMetadataError(
    ArchiveValidationError
):
    pass



# Phase B



class ArchiveIntegrityError(
    ArchiveValidationError
):
    pass


class ArchiveBombError(
    ArchiveValidationError
):
    pass


class CompressionRatioExceededError(
    ArchiveValidationError
):
    pass


class ExtractedSizeExceededError(
    ArchiveValidationError
):
    pass


class EntrySizeExceededError(
    ArchiveValidationError
):
    pass


class FileCountExceededError(
    ArchiveValidationError
):
    pass


class ArchiveDepthExceededError(
    ArchiveValidationError
):
    pass


class PasswordProtectedArchiveError(
    ArchiveValidationError
):
    pass


class EncryptedArchiveError(
    ArchiveValidationError
):
    pass


class PathTraversalError(
    ArchiveValidationError
):
    pass


class AbsolutePathError(
    ArchiveValidationError
):
    pass


class SymbolicLinkError(
    ArchiveValidationError
):
    pass


class HardLinkError(
    ArchiveValidationError
):
    pass


class DuplicateEntryError(
    ArchiveValidationError
):
    pass


class UnsupportedEntryError(
    ArchiveValidationError
):
    pass


class UnsafeArchiveFilenameError(
    ArchiveValidationError
):
    pass


class EmptyArchiveError(
    ArchiveValidationError
):
    pass



# Operational Errors



class StageTwoOperationalError(StageTwoError):
    """
    Stage 2 could not complete because our system or
    infrastructure failed.

    These failures should NOT automatically cause deletion of
    the quarantine object.
    """


class ArchiveReadError(
    StageTwoOperationalError
):
    pass


class WorkspaceCreationError(
    StageTwoOperationalError
):
    pass


class ArchiveExtractionError(
    StageTwoOperationalError
):
    pass


class ChildRegistrationError(
    StageTwoOperationalError
):
    pass


class ChildQueueError(
    StageTwoOperationalError
):
    pass


class StageTwoStorageError(
    StageTwoOperationalError
):
    pass


class StageTwoPipelineError(
    StageTwoOperationalError
):
    pass