from app.knowledge.security.stage_2.constants import (
    ALLOW_ENCRYPTED_ARCHIVES,
    PHASE_SECURITY,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    EncryptedArchiveError,
    PasswordProtectedArchiveError,
)


def detect_encryption(
    context: ArchiveValidationContext,
) -> None:
    """
    Detect encrypted entries using metadata collected during
    Phase A and update the Stage 2 context.

    This function detects encryption only. Policy enforcement
    is handled separately by validate_encryption_policy().
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "encryption_detection"

    encrypted_entries = [
        entry
        for entry in context.entries
        if entry.is_encrypted
    ]

    context.encrypted = bool(encrypted_entries)

    # For the currently supported ZIP metadata model, encrypted
    # members require credentials before their contents can be
    # inspected/extracted, so they are treated as protected.
    context.password_protected = context.encrypted


def validate_encryption_policy(
    context: ArchiveValidationContext,
) -> None:
    """
    Enforce the configured archive encryption policy.

    Our current ingestion policy rejects encrypted archives
    because Stage 2 must be able to inspect and validate every
    child before allowing it further into the pipeline.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "encryption_policy_validation"

    if not context.encrypted:
        return

    if ALLOW_ENCRYPTED_ARCHIVES:
        return

    encrypted_entries = [
        entry.name
        for entry in context.entries
        if entry.is_encrypted
    ]

    raise EncryptedArchiveError(
        (
            f"Archive '{context.original_filename}' contains "
            f"encrypted content and encrypted archives are not "
            f"allowed."
        ),
        phase=PHASE_SECURITY,
        check="encryption_policy_validation",
        code="ENCRYPTED_ARCHIVE_NOT_ALLOWED",
        details={
            "encrypted_entry_count": len(encrypted_entries),
            "encrypted_entries": encrypted_entries[:100],
        },
    )


def validate_password_protection(
    context: ArchiveValidationContext,
) -> None:
    """
    Reject password-protected archives according to the current
    Stage 2 policy.

    This remains a separate check so audit logs can distinguish
    password protection from other encryption policies when
    additional archive handlers are added later.
    """

    context.current_phase = PHASE_SECURITY
    context.current_check = "password_protection_validation"

    if not context.password_protected:
        return

    if ALLOW_ENCRYPTED_ARCHIVES:
        return

    raise PasswordProtectedArchiveError(
        (
            f"Archive '{context.original_filename}' is "
            f"password-protected and cannot be safely inspected."
        ),
        phase=PHASE_SECURITY,
        check="password_protection_validation",
        code="PASSWORD_PROTECTED_ARCHIVE_NOT_ALLOWED",
    )


def validate_archive_encryption(
    context: ArchiveValidationContext,
) -> None:
    """
    Run Stage 2 encryption/password-protection checks.
    """

    detect_encryption(context)

    # Password protection is the more specific condition in our
    # current metadata model, so enforce it first.
    validate_password_protection(context)

    validate_encryption_policy(context)