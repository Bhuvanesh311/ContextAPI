import logging
from collections.abc import Callable

from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import (
    IntegrityValidationError,
)

logger = logging.getLogger(__name__)


DuplicateLookup = Callable[[str, str, str],str | None,]


def check_duplicate_file(context: ValidationContext,lookup_duplicate: DuplicateLookup,) -> None:

    if not context.sha256:
        raise IntegrityValidationError(
            f"SHA-256 hash is unavailable for "
            f"'{context.original_filename}'.",
            phase="integrity_trust",
            check="duplicate_detection",
            code="HASH_UNAVAILABLE",
        )

    try:
        existing_document_id = lookup_duplicate(
                                                    context.project_id,
                                                    context.document_id,
                                                    context.sha256,
                                                )

    except Exception as exc:
        raise IntegrityValidationError(
        f"Duplicate lookup failed for "
        f"'{context.original_filename}': {exc}",
        phase="integrity_trust",
        check="duplicate_detection",
        code="DUPLICATE_LOOKUP_FAILED",
    ) from exc

    if existing_document_id is not None:
        # Uploading the same file again is allowed: it is indexed as its own
        # document. Retrieval and context assembly drop identical chunks, so
        # the copies do not crowd out other results.
        context.duplicate = True
        context.duplicate_document_id = str(existing_document_id)
        logger.info(
            "Duplicate content accepted | document=%s | duplicate_of=%s",
            context.document_id,
            context.duplicate_document_id,
        )
        return

    context.duplicate = False
    context.duplicate_document_id = None