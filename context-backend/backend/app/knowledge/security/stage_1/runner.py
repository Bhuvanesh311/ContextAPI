from sqlalchemy.orm import Session

from app.knowledge.uploads.models import Document,DocumentVersion
from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.pipeline import run_stage_one
from app.knowledge.security.stage_1.integration.duplicate_db import (
    find_duplicate_document,
)
from app.knowledge.security.stage_1.integration.storage_adapter import (
    download_to_temp_file,
)

def run_stage_one_for_document(db: Session,document: Document,document_version: DocumentVersion,) -> ValidationContext:

    temp_path = download_to_temp_file(
        bucket = document_version.quarantine_bucket,
        object_key = document_version.quarantine_object_key,
        suffix=document_version.file_extension,
    )

    try:
        context = ValidationContext(
            upload_id=document.upload_id,
            project_id=document.project_id,
            document_id=document.document_id,
            file_path=temp_path,
            original_filename=document.original_filename,
            declared_mime=document.mime_type,
        )

        def duplicate_lookup(project_id: str,document_id: str,sha256: str,) -> str | None:
            return find_duplicate_document(
                db,
                project_id=project_id,
                checksum=sha256,
                exclude_document_id=document_id,
            )

        return run_stage_one(
            context,
            lookup_duplicate=duplicate_lookup,
        )

    finally:
        temp_path.unlink(missing_ok=True)