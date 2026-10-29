import hashlib

from app.knowledge.security.stage_1.constants import (
    HASH_ALGORITHM,
    HASH_CHUNK_SIZE,
)
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import HashGenerationError


def generate_file_hash(context: ValidationContext) -> None:

    try:
        hasher = hashlib.new(HASH_ALGORITHM)

        with context.file_path.open("rb") as file:
            while chunk := file.read(HASH_CHUNK_SIZE):
                hasher.update(chunk)

        context.sha256 = hasher.hexdigest()

    except (OSError, ValueError) as exc:
        raise HashGenerationError(
            f"Unable to generate {HASH_ALGORITHM.upper()} hash for "
            f"'{context.original_filename}'.",
            phase="integrity_trust",
            check="hash_generation",
            code="HASH_GENERATION_FAILED",
        ) from exc