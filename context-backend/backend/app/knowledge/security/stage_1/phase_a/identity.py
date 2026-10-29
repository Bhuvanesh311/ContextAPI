from pathlib import Path

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import (
    FileNotFoundValidationError,
    IdentityValidationError,
)


def validate_file_identity(context: ValidationContext) -> None:

    file_path = context.file_path

    if not file_path.exists():
        raise FileNotFoundValidationError(
            f"File '{context.original_filename}' does not exist.",
            phase="identity_metadata",
            check="file_exists",
            code="FILE_NOT_FOUND",
        )

    if not file_path.is_file():
        raise IdentityValidationError(
            f"Path for '{context.original_filename}' is not a regular file.",
            phase="identity_metadata",
            check="file_type",
            code="NOT_REGULAR_FILE",
        )