from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import (
    DocumentStatus,
    DocumentVersionStatus,
    IngestionRunStatus,
    IngestionStage,
)

from app.infra.storage import storage_service

from app.knowledge.uploads.models import (
    Document,
    DocumentVersion,
    IngestionRun,
)
from app.knowledge.uploads.utils import (
    get_next_document_sequence,
    generate_document_id,
    get_next_document_version_sequence,
    generate_document_version_id,
    get_next_ingestion_run_sequence,
    generate_ingestion_run_id,
    generate_storage_filename,
    get_file_extension,
    normalize_filename,
)

from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)



# Metadata helpers



def _calculate_file_checksum(
    path: Path,
) -> str:
    """
    Calculate SHA-256 without loading the entire extracted file
    into memory.
    """

    hasher = hashlib.sha256()

    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            hasher.update(chunk)

    return hasher.hexdigest()


def _detect_mime_type(
    path: Path,
) -> str:
    """
    Best-effort MIME value for the initial Document row.

    Stage 1 will perform the authoritative MIME/magic detection.
    """

    mime_type, _ = mimetypes.guess_type(
        path.name
    )

    return (
        mime_type
        or "application/octet-stream"
    )



# Child identity



def prepare_child_identity(
    db: Session,
    child: ChildFileContext,
) -> str:
    """
    Allocate the real DOCxxxxxx identifier for an extracted child.

    This does not insert the Document yet.
    """

    if child.document_id:
        return child.document_id

    sequence = get_next_document_sequence(
        db
    )

    document_id = generate_document_id(
        sequence
    )

    child.document_id = document_id

    return document_id



# Object key



def build_child_object_key(
    child: ChildFileContext,
    storage_filename: str,
) -> str:

    if not child.document_id:
        raise ValueError(
            "Child document_id must exist before "
            "building object key."
        )

    return (
        f"projects/{child.project_id}/"
        f"uploads/{child.upload_id}/"
        f"documents/{child.document_id}/"
        f"{storage_filename}"
    )



# MinIO storage



def store_child_file(
    child: ChildFileContext,
) -> str:
    """
    Upload an extracted child into quarantine storage.

    Returns its MinIO object key.
    """

    source_path = Path(
        child.source_path
    )

    if not source_path.exists():
        raise FileNotFoundError(
            f"Extracted child does not exist: "
            f"{source_path}"
        )

    if not source_path.is_file():
        raise ValueError(
            f"Extracted child is not a file: "
            f"{source_path}"
        )

    if not child.document_id:
        raise ValueError(
            "Child document_id has not been prepared."
        )

    extension = get_file_extension(
        child.original_filename
    )

    storage_filename = (
        generate_storage_filename(
            document_id=child.document_id,
            extension=extension,
        )
    )

    object_key = build_child_object_key(
        child,
        storage_filename,
    )

    file_size = source_path.stat().st_size

    mime_type = _detect_mime_type(
        source_path
    )

    with source_path.open("rb") as stream:

        storage_service.upload(
            bucket=settings.MINIO_QUARANTINE_BUCKET,
            object_key=object_key,
            data=stream,
            size=file_size,
            content_type=mime_type,
        )

    child.storage_key = object_key
    child.stored = True

    return object_key



# PostgreSQL registration


def register_child_document(
    db: Session,
    *,
    parent_document: Document,
    child: ChildFileContext,
) -> str:
    """
    Persist one extracted child as a Document, DocumentVersion,
    and initial IngestionRun.

    The child has already been stored in quarantine before this
    function is called.
    """

    if not child.document_id:
        raise ValueError(
            "Child document_id has not been prepared."
        )

    if not child.storage_key:
        raise ValueError(
            "Child has not been stored in quarantine."
        )

    source_path = Path(child.source_path)

    if not source_path.exists():
        raise FileNotFoundError(
            f"Extracted child disappeared before "
            f"registration: {source_path}"
        )

    original_filename = normalize_filename(
        child.original_filename
    )

    extension = get_file_extension(
        original_filename
    )

    checksum = _calculate_file_checksum(
        source_path
    )

    file_size = source_path.stat().st_size

    mime_type = _detect_mime_type(
        source_path
    )

    document = Document(
        document_id=child.document_id,
        upload_id=parent_document.upload_id,
        project_id=parent_document.project_id,
        user_id=parent_document.user_id,
        parent_document_id=parent_document.document_id,
        name=original_filename,
        original_filename=original_filename,
        mime_type=mime_type,
        status=DocumentStatus.ACTIVE,
    )

    db.add(document)
    db.flush()

    document_version_sequence = (
        get_next_document_version_sequence(db)
    )

    document_version_id = (
        generate_document_version_id(
            document_version_sequence
        )
    )

    document_version = DocumentVersion(
        document_version_id=document_version_id,
        document_id=document.document_id,
        version_number=1,
        file_name=original_filename,
        mime_type=mime_type,
        file_extension=extension,
        file_size=file_size,
        sha256_hash=checksum,
        source_type="UPLOAD",
        source_reference=None,

        quarantine_bucket=(
            settings.MINIO_QUARANTINE_BUCKET
        ),
        quarantine_object_key=child.storage_key,

        permanent_bucket=None,
        permanent_object_key=None,

        parsed_bucket=None,
        parsed_object_key=None,
        parsed_format=None,

        status=DocumentVersionStatus.CREATED,
    )

    db.add(document_version)
    db.flush()

    document.current_version_id = (
        document_version.document_version_id
    )

    ingestion_run_sequence = (
        get_next_ingestion_run_sequence(db)
    )

    ingestion_run_id = (
        generate_ingestion_run_id(
            ingestion_run_sequence
        )
    )

    ingestion_run = IngestionRun(
        ingestion_run_id=ingestion_run_id,
        document_id=document.document_id,
        document_version_id=(
            document_version.document_version_id
        ),
        status=IngestionRunStatus.PENDING,
        current_stage=IngestionStage.UPLOAD_RECEIVED,
        attempt_number=1,
        retry_count=0,
        max_retries=3,
    )

    db.add(ingestion_run)
    db.flush()

    child.registered = True

    return document.document_id


# Rollback MinIO object



def delete_child_object(
    child: ChildFileContext,
) -> None:
    """
    Compensation when MinIO upload succeeded but DB registration
    failed.

    We don't want orphaned child objects in quarantine.
    """

    if not child.storage_key:
        return

    storage_service.delete(
        bucket=settings.MINIO_QUARANTINE_BUCKET,
        object_key=child.storage_key,
    )

    child.storage_key = None
    child.stored = False



# Persist child



def persist_child(
    db: Session,
    *,
    parent_document: Document,
    child: ChildFileContext,
) -> str:
    """
    Prepare, store and register one extracted child.

    Storage happens before DB registration because the Document
    schema requires storage_bucket/object_key.

    If DB registration fails after MinIO upload, the uploaded
    object is removed as compensation.
    """

    prepare_child_identity(
        db,
        child,
    )

    store_child_file(
        child
    )

    try:

        return register_child_document(
            db,
            parent_document=parent_document,
            child=child,
        )

    except Exception:

        delete_child_object(
            child
        )

        raise