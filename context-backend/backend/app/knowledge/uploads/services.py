import io
import logging
from datetime import datetime, timezone
from pathlib import PurePath

from app.core.config import settings
from app.knowledge.uploads.text_encoding import (
    MAX_NORMALIZE_BYTES,
    TEXT_EXTENSIONS,
    normalize_to_utf8,
)
from app.infra.storage import storage_service

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy import asc, desc, text

from fastapi import HTTPException, UploadFile, status

from app.auth.models import User

from app.knowledge.uploads.models import (
    UploadJob,
    Document,
    DocumentVersion,
    IngestionRun,
    KnowledgeProcessingRun,
)

from app.knowledge.uploads.schemas import (
    UploadRequest,
    PaginationMeta,
    UpdateDocumentRequest,
)

from app.core.enums import (
    UploadStatus,
    DocumentStatus,
    DocumentVersionStatus,
    IngestionRunStatus,
    IngestionStage,
    KnowledgeProcessingRunStatus,
)

from app.knowledge.uploads.utils import (
    get_next_upload_sequence,
    generate_upload_id,
    get_next_document_sequence,
    generate_document_id,
    get_next_document_version_sequence,
    generate_document_version_id,
    get_next_ingestion_run_sequence,
    generate_ingestion_run_id,
    normalize_filename,
    get_file_extension,
    generate_storage_filename,
)

from app.knowledge.uploads.tasks import (
    run_ingestion_task,
)
from app.knowledge.uploads.constants import (
    ALLOWED_FILE_EXTENSIONS,
    BLOCKED_FILE_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_FILES_PER_UPLOAD,
    MAX_FILENAME_LENGTH,
)
from app.project.models import Project

import hashlib
import math


def _get_document_or_404(
    db: Session,
    document_id: str,
) -> Document:

    document = (
        db.query(Document)
        .filter(
            Document.document_id == document_id
        )
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return document


def _get_upload_or_404(
    db: Session,
    upload_id: str,
) -> UploadJob:

    upload = (
        db.query(UploadJob)
        .filter(
            UploadJob.upload_id == upload_id
        )
        .first()
    )

    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found.",
        )

    return upload


def _verify_document_ownership(
    current_user: User,
    document: Document,
) -> None:

    if document.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document.",
        )


def _verify_upload_ownership(
    current_user: User,
    upload: UploadJob,
) -> None:

    if upload.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this upload.",
        )


def _create_upload_job(
    db: Session,
    current_user: User,
    project_id: str,
    total_files: int,
) -> UploadJob:

    sequence = get_next_upload_sequence(db)

    upload_id = generate_upload_id(sequence)

    upload_job = UploadJob(
        upload_id=upload_id,
        project_id=project_id,
        user_id=current_user.user_id,
        total_files=total_files,
        processed_files=0,
        failed_files=0,
        status=UploadStatus.QUEUED,
    )

    db.add(upload_job)

    db.flush()

    return upload_job


def _store_file(
    *,
    file: UploadFile,
    project_id: str,
    upload_id: str,
    document_id: str,
    storage_filename: str,
) -> tuple[str, str, str, int]:

    bucket = settings.MINIO_QUARANTINE_BUCKET

    object_key = (
        f"projects/{project_id}/"
        f"uploads/{upload_id}/"
        f"documents/{document_id}/"
        f"{storage_filename}"
    )

    # Text files in UTF-16 / Windows-1252 / with a BOM are stored as UTF-8
    # so every validator and parser can read them.
    extension = PurePath(storage_filename).suffix
    if extension.lower() in TEXT_EXTENSIONS:
        raw = file.file.read(MAX_NORMALIZE_BYTES + 1)
        converted = normalize_to_utf8(raw, extension)
        file.file.seek(0)
        if converted is not None:
            file.file = io.BytesIO(converted)

    hasher = hashlib.sha256()
    file_size = 0

    while chunk := file.file.read(1024 * 1024):
        hasher.update(chunk)
        file_size += len(chunk)

    checksum = hasher.hexdigest()

    file.file.seek(0)

    storage_service.upload(
        bucket=bucket,
        object_key=object_key,
        data=file.file,
        size=file_size,
        content_type=(
            file.content_type
            or "application/octet-stream"
        ),
    )

    file.file.seek(0)

    return (
        bucket,
        object_key,
        checksum,
        file_size,
    )


def _process_file(
    db: Session,
    current_user: User,
    upload_job: UploadJob,
    project_id: str,
    file: UploadFile,
) -> str:

    document_sequence = (
        get_next_document_sequence(db)
    )

    document_id = generate_document_id(
        document_sequence
    )

    original_filename = normalize_filename(
        file.filename
    )

    extension = get_file_extension(
        original_filename
    )

    storage_filename = generate_storage_filename(
        document_id=document_id,
        extension=extension,
    )

    (
        bucket,
        object_key,
        checksum,
        file_size,
    ) = _store_file(
        file=file,
        project_id=project_id,
        upload_id=upload_job.upload_id,
        document_id=document_id,
        storage_filename=storage_filename,
    )

    document = Document(
        document_id=document_id,
        upload_id=upload_job.upload_id,
        project_id=project_id,
        user_id=current_user.user_id,
        parent_document_id=None,
        name=original_filename,
        original_filename=original_filename,
        mime_type=(
            file.content_type
            or "application/octet-stream"
        ),
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

    parsed_bucket = settings.MINIO_PARSED_BUCKET

    parsed_object_key = (
        f"projects/{project_id}/"
        f"documents/{document_id}/"
        f"versions/{document_version_id}/"
        f"parsed.json"
    )
    
    document_version = DocumentVersion(
        document_version_id=document_version_id,
        document_id=document.document_id,
        version_number=1,
        file_name=original_filename,
        mime_type=(
            file.content_type
            or "application/octet-stream"
        ),
        file_extension=extension,
        file_size=file_size,
        sha256_hash=checksum,
        source_type="UPLOAD",
        source_reference=None,
    
        quarantine_bucket=bucket,
        quarantine_object_key=object_key,
    
        permanent_bucket=None,
        permanent_object_key=None,
    
        parsed_bucket=parsed_bucket,
        parsed_object_key=parsed_object_key,
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
        current_stage=(
            IngestionStage.UPLOAD_RECEIVED
        ),
        attempt_number=1,
        retry_count=0,
        max_retries=3,
    )

    db.add(ingestion_run)

    upload_job.processed_files += 1

    db.flush()

    return ingestion_run.ingestion_run_id


# Compound archive suffixes that Path.suffix reports only as ".gz".
_ARCHIVE_SUFFIXES = (".tar.gz", ".tgz")


def _file_size(file: UploadFile) -> int:
    if file.size is not None:
        return file.size
    file.file.seek(0, io.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    return size


def _validate_upload(
    db: Session,
    current_user: User,
    project_id: str,
    files: list[UploadFile],
) -> None:
    """
    Reject a bad request before anything is stored: a project the caller does
    not own, too many files, or a file that ingestion would reject anyway.
    """
    project = (
        db.query(Project)
        .filter(Project.project_id == project_id, Project.user_id == current_user.user_id)
        .first()
    )
    if project is None:
        # Same answer for "missing" and "someone else's": no information leak.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files were sent.")
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Too many files: {len(files)}. Upload at most {MAX_FILES_PER_UPLOAD} files at a time.",
        )

    problems: list[str] = []
    for file in files:
        name = normalize_filename(file.filename or "")
        lower = name.lower()
        extension = get_file_extension(name)
        size = _file_size(file)
        if not name:
            problems.append("A file has no name.")
        elif len(name) > MAX_FILENAME_LENGTH:
            problems.append(f"'{name[:40]}…' has a name longer than {MAX_FILENAME_LENGTH} characters.")
        elif extension in BLOCKED_FILE_EXTENSIONS:
            problems.append(f"'{name}' is not allowed: {extension} files can contain programs.")
        elif extension not in ALLOWED_FILE_EXTENSIONS and not lower.endswith(_ARCHIVE_SUFFIXES):
            problems.append(f"'{name}' is not a supported file type ({extension or 'no extension'}).")
        elif size == 0:
            problems.append(f"'{name}' is empty.")
        elif size > MAX_FILE_SIZE:
            problems.append(
                f"'{name}' is {size / (1024 * 1024):.0f} MB; the limit is {MAX_FILE_SIZE // (1024 * 1024)} MB per file."
            )
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=" ".join(problems))


def upload_documents(
    db: Session,
    current_user: User,
    request: UploadRequest,
    files: list[UploadFile],
) -> UploadJob:

    _validate_upload(db, current_user, request.project_id, files)

    try:

        upload_job = _create_upload_job(
            db=db,
            current_user=current_user,
            project_id=request.project_id,
            total_files=len(files),
        )

        ingestion_run_ids: list[str] = []

        for file in files:

            ingestion_run_id = _process_file(
                db=db,
                current_user=current_user,
                upload_job=upload_job,
                project_id=request.project_id,
                file=file,
            )

            ingestion_run_ids.append(
                ingestion_run_id
            )

        db.commit()

        for ingestion_run_id in ingestion_run_ids:

            run_ingestion_task.delay(
                ingestion_run_id
            )

        return upload_job

    except SQLAlchemyError as exc:

        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Database error occurred "
                "while uploading documents."
            ),
        ) from exc

    except Exception:

        db.rollback()

        raise


def list_uploads(
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[UploadJob], PaginationMeta]:

    query = (
        db.query(UploadJob)
        .filter(
            UploadJob.user_id == current_user.user_id
        )
        .order_by(
            desc(UploadJob.created_at)
        )
    )

    total_records = query.count()

    uploads = (
        query
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
        .all()
    )

    total_pages = (
        math.ceil(
            total_records / page_size
        )
        if total_records > 0
        else 0
    )

    pagination = PaginationMeta(
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )

    return uploads, pagination


def get_upload_details(
    db: Session,
    current_user: User,
    upload_id: str,
):

    upload = _get_upload_or_404(
        db=db,
        upload_id=upload_id,
    )

    _verify_upload_ownership(
        current_user=current_user,
        upload=upload,
    )

    documents = (
        db.query(Document)
        .filter(
            Document.upload_id
            == upload.upload_id
        )
        .order_by(
            desc(Document.created_at)
        )
        .all()
    )

    return upload, documents


def list_documents(
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    project_id: str | None = None,
    status_filter: DocumentStatus | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
) -> tuple[list[Document], PaginationMeta]:

    query = (
        db.query(Document)
        .filter(
            Document.user_id
            == current_user.user_id
        )
    )

    if project_id:

        query = query.filter(
            Document.project_id == project_id
        )

    if status_filter:

        query = query.filter(
            Document.status == status_filter
        )

    if search:

        query = query.filter(
            Document.original_filename.ilike(
                f"%{search}%"
            )
        )

    allowed_sort_fields = {
        "created_at": Document.created_at,
        "updated_at": Document.updated_at,
        "filename": Document.original_filename,
        "name": Document.name,
        "status": Document.status,
    }

    sort_column = allowed_sort_fields.get(
        sort_by,
        Document.created_at,
    )

    if order.lower() == "asc":

        query = query.order_by(
            asc(sort_column)
        )

    else:

        query = query.order_by(
            desc(sort_column)
        )

    total_records = query.count()

    documents = (
        query
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
        .all()
    )

    total_pages = (
        math.ceil(
            total_records / page_size
        )
        if total_records > 0
        else 0
    )

    pagination = PaginationMeta(
        page=page,
        page_size=page_size,
        total_records=total_records,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1,
    )

    return documents, pagination


def get_document(
    db: Session,
    current_user: User,
    document_id: str,
) -> Document:

    document = _get_document_or_404(
        db=db,
        document_id=document_id,
    )

    _verify_document_ownership(
        current_user=current_user,
        document=document,
    )

    return document


def rename_document(
    db: Session,
    current_user: User,
    document_id: str,
    request: UpdateDocumentRequest,
) -> Document:

    document = _get_document_or_404(
        db=db,
        document_id=document_id,
    )

    _verify_document_ownership(
        current_user=current_user,
        document=document,
    )

    document.name = request.original_filename
    document.original_filename = (
        request.original_filename
    )

    db.commit()

    db.refresh(document)

    return document


logger = logging.getLogger(__name__)

# The collection the ingestion pipeline indexes into (vector_indexing.py).
VECTOR_COLLECTION = "knowledge"
_VECTOR_DELETE_BATCH = 500


def stored_objects(
    versions: list[DocumentVersion],
) -> list[tuple[str, str]]:
    """(bucket, object_key) of every file stored for these versions."""

    objects = []

    for version in versions:
        for bucket, key in (
            (version.quarantine_bucket, version.quarantine_object_key),
            (version.permanent_bucket, version.permanent_object_key),
            (version.parsed_bucket, version.parsed_object_key),
        ):
            if bucket and key:
                objects.append((bucket, key))

    return objects


def purge_stored_files(
    objects: list[tuple[str, str]],
    version_ids: list[str],
) -> None:
    """
    Best-effort removal of deleted documents' files (object storage) and
    vectors (ChromaDB). Call after the database rows are committed as deleted;
    leftovers are logged, never raised, since the delete already happened.
    Search can't reach leftovers: it is scoped to live document versions.
    """

    for bucket, key in objects:
        try:
            storage_service.delete(bucket=bucket, object_key=key)
        except Exception:
            logger.warning(
                "Could not delete stored object %s/%s", bucket, key,
                exc_info=True,
            )

    if not version_ids:
        return

    try:
        from app.infra.chromadb.client import chroma_client

        collection = chroma_client.get_collection(VECTOR_COLLECTION)

        for i in range(0, len(version_ids), _VECTOR_DELETE_BATCH):
            collection.delete(
                where={
                    "document_version_id": {
                        "$in": version_ids[i:i + _VECTOR_DELETE_BATCH],
                    }
                }
            )
    except Exception:
        logger.warning(
            "Could not delete vectors of %d document version(s)",
            len(version_ids),
            exc_info=True,
        )


def _document_tree_ids(db: Session, document_id: str) -> list[str]:
    """The document and, for an archive, every member below it."""

    document_ids = [document_id]
    frontier = document_ids[:]
    while frontier:
        frontier = [
            row.document_id
            for row in db.query(Document.document_id)
            .filter(Document.parent_document_id.in_(frontier))
            .all()
        ]
        document_ids.extend(frontier)

    return document_ids


_ACTIVE_INGESTION = (
    IngestionRunStatus.PENDING,
    IngestionRunStatus.RUNNING,
    IngestionRunStatus.RETRYING,
)
_ACTIVE_PROCESSING = (
    KnowledgeProcessingRunStatus.PENDING,
    KnowledgeProcessingRunStatus.RUNNING,
    KnowledgeProcessingRunStatus.RETRYING,
)


def cancel_document(
    db: Session,
    current_user: User,
    document_id: str,
) -> Document:
    """
    Stop a document's ingestion and indexing now (for an archive, also every
    member still in progress). See app/knowledge/cancellation.py for how the
    running work is stopped. The document is left FAILED with
    "Stopped by user." and can be deleted or uploaded again.
    """

    from app.infra.celery.app import celery_app
    from app.knowledge.cancellation import (
        CANCELLED_CODE,
        CANCELLED_MESSAGE,
        mark_cancelled,
        task_for,
    )

    document = _get_document_or_404(
        db=db,
        document_id=document_id,
    )

    _verify_document_ownership(
        current_user=current_user,
        document=document,
    )

    document_ids = _document_tree_ids(db, document.document_id)
    version_ids = [
        version_id
        for (version_id,) in db.query(DocumentVersion.document_version_id)
        .filter(DocumentVersion.document_id.in_(document_ids))
    ]

    ingestion_ids = [
        run_id
        for (run_id,) in db.query(IngestionRun.ingestion_run_id).filter(
            IngestionRun.document_id.in_(document_ids),
            IngestionRun.status.in_(_ACTIVE_INGESTION),
        )
    ]
    processing_ids = [
        run_id
        for (run_id,) in db.query(
            KnowledgeProcessingRun.knowledge_processing_run_id
        ).filter(
            KnowledgeProcessingRun.document_version_id.in_(version_ids),
            KnowledgeProcessingRun.status.in_(_ACTIVE_PROCESSING),
        )
    ]

    if not ingestion_ids and not processing_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is not being processed.",
        )

    # 1. Flag first: work that can't be killed checks it between steps.
    mark_cancelled(version_ids)

    # 2. Kill ingestion task processes (prefork worker) and drop queued
    #    indexing tasks. A running indexing task (threads) stops on the flag.
    killed = False
    for run_id in ingestion_ids:
        task_id = task_for(run_id)
        if task_id:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGKILL")
            killed = True
    for run_id in processing_ids:
        task_id = task_for(run_id)
        if task_id:
            celery_app.control.revoke(task_id)

    # 3. Record the stop. A killed process's transaction is rolled back by
    #    Postgres when its connection drops, releasing its row locks; wait for
    #    that briefly. An indexing run still held by its thread is skipped and
    #    recorded by the task itself when it sees the flag.
    now = datetime.now(timezone.utc)
    try:
        db.execute(text("SET LOCAL lock_timeout = '10s'"))

        for run in (
            db.query(IngestionRun)
            .filter(
                IngestionRun.ingestion_run_id.in_(ingestion_ids),
                IngestionRun.status.in_(_ACTIVE_INGESTION),
            )
            .with_for_update()
        ):
            run.status = IngestionRunStatus.CANCELLED
            run.error_code = CANCELLED_CODE
            run.error_message = CANCELLED_MESSAGE
            run.next_retry_at = None
            run.updated_at = now

        for run in (
            db.query(KnowledgeProcessingRun)
            .filter(
                KnowledgeProcessingRun.knowledge_processing_run_id.in_(processing_ids),
                KnowledgeProcessingRun.status.in_(_ACTIVE_PROCESSING),
            )
            .with_for_update(skip_locked=True)
        ):
            run.status = KnowledgeProcessingRunStatus.CANCELLED
            run.error_code = CANCELLED_CODE
            run.error_message = CANCELLED_MESSAGE
            run.updated_at = now

        # Members already indexed stay usable; the rest are out of search.
        stopped_versions = set(
            version_id
            for (version_id,) in db.query(KnowledgeProcessingRun.document_version_id)
            .filter(
                KnowledgeProcessingRun.knowledge_processing_run_id.in_(processing_ids)
            )
        )
        stopped_documents = set(
            doc_id
            for (doc_id,) in db.query(IngestionRun.document_id).filter(
                IngestionRun.ingestion_run_id.in_(ingestion_ids)
            )
        ) | set(
            doc_id
            for (doc_id,) in db.query(DocumentVersion.document_id).filter(
                DocumentVersion.document_version_id.in_(stopped_versions)
            )
        )
        db.query(Document).filter(
            Document.document_id.in_(stopped_documents),
            Document.status == DocumentStatus.ACTIVE,
        ).update(
            {Document.status: DocumentStatus.FAILED, Document.updated_at: now},
            synchronize_session=False,
        )

        db.commit()

    except OperationalError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not stop the document right now. Try again.",
        )

    # 4. Partly indexed vectors, and the parser sandbox of a killed task.
    stopped_version_ids = [
        version_id
        for (version_id,) in db.query(DocumentVersion.document_version_id)
        .filter(DocumentVersion.document_id.in_(stopped_documents))
    ]
    purge_stored_files([], stopped_version_ids)
    if killed:
        celery_app.send_task("knowledge.cleanup_sandboxes", countdown=2)

    db.refresh(document)
    return document


def delete_document(
    db: Session,
    current_user: User,
    document_id: str,
) -> None:

    document = _get_document_or_404(
        db=db,
        document_id=document_id,
    )

    _verify_document_ownership(
        current_user=current_user,
        document=document,
    )

    # Archive members are child documents; the database cascade deletes
    # them too, so their files and vectors go as well.
    document_ids = _document_tree_ids(db, document.document_id)

    versions = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.document_id.in_(document_ids)
        )
        .all()
    )
    objects = stored_objects(versions)
    version_ids = [v.document_version_id for v in versions]

    db.delete(document)

    db.commit()

    # Files and vectors go only once the rows are gone, so a failed commit
    # never leaves a document pointing at deleted files.
    purge_stored_files(objects, version_ids)