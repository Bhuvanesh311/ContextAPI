from sqlalchemy.orm import Session

from app.core.enums import DocumentStatus
from app.knowledge.uploads.models import (
    Document,
    DocumentVersion,
)

_NOT_INDEXED = (
    DocumentStatus.REJECTED,
    DocumentStatus.FAILED,
    DocumentStatus.DELETED,
)


def find_duplicate_document(
    db: Session,
    *,
    project_id: str,
    checksum: str,
    exclude_document_id: str,
) -> str | None:

    duplicate = (
        db.query(Document.document_id)
        .join(
            DocumentVersion,
            DocumentVersion.document_id
            == Document.document_id,
        )
        .filter(
            Document.project_id == project_id,
            DocumentVersion.sha256_hash == checksum,
            Document.document_id != exclude_document_id,
            # A rejected or failed copy was never indexed: uploading the
            # same file again must be allowed.
            Document.status.notin_(_NOT_INDEXED),
        )
        .first()
    )

    if duplicate is None:
        return None

    return duplicate[0]