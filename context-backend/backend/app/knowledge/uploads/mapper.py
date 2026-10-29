from app.core.enums import (
    DocumentStatus,
    IngestionRunStatus,
    KnowledgeProcessingRunStatus,
)
from app.knowledge.uploads.models import (
    UploadJob,
    Document,
)

from app.knowledge.uploads.schemas import (
    UploadResponse,
    DocumentResponse,
    DocumentDetailResponse,
    UploadHistoryResponse,
    UploadDetailResponse,
)


def map_upload_response(
    upload_job: UploadJob,
) -> UploadResponse:

    return UploadResponse(
        upload_id=upload_job.upload_id,
        total_files=upload_job.total_files,
    )


def _get_current_version(
    document: Document,
):
    """
    Return the current document version.

    The current document model stores file-level metadata
    on DocumentVersion, not on Document.
    """

    version = document.current_version

    if version is None:
        raise ValueError(
            f"Document {document.document_id} "
            "does not have a current version."
        )

    return version


def _latest(runs):
    runs = list(runs or [])
    return max(runs, key=lambda r: r.created_at) if runs else None


def _with_code(code, message):
    """'CODE: message', unless the message already starts with the code."""
    if not code or (message or "").startswith(f"{code}:"):
        return message
    return f"{code}: {message}"


def _indexing_state(document: Document, version) -> dict:
    """Where the document is in ingestion -> indexing, and why it failed."""
    ingestion = _latest(document.ingestion_runs)
    processing = _latest(version.knowledge_processing_runs)

    if document.status == DocumentStatus.FAILED and any(
        run is not None and run.status in (IngestionRunStatus.CANCELLED, KnowledgeProcessingRunStatus.CANCELLED)
        for run in (ingestion, processing)
    ):
        return {"indexing_status": "CANCELLED", "status_reason": "Stopped by user."}

    if document.status in (DocumentStatus.REJECTED, DocumentStatus.FAILED):
        failed = ingestion if ingestion is not None and ingestion.error_message else processing
        reason = None
        if failed is not None and failed.error_message:
            reason = _with_code(failed.error_code, failed.error_message)
        return {"indexing_status": document.status.value, "status_reason": reason}

    if ingestion is not None and ingestion.status != IngestionRunStatus.COMPLETED:
        return {"indexing_status": "INGESTING", "status_reason": None}

    # An archive is unpacked into child documents and is never indexed itself;
    # without this it showed INDEXING forever.
    if ingestion is not None and (ingestion.checkpoint_data or {}).get("archive_completed"):
        return {"indexing_status": "READY", "status_reason": "Archive unpacked; its files are listed separately."}

    if processing is None:
        return {"indexing_status": "INDEXING", "status_reason": None}
    if processing.status == KnowledgeProcessingRunStatus.COMPLETED:
        return {"indexing_status": "READY", "status_reason": None}
    if processing.status in (KnowledgeProcessingRunStatus.FAILED, KnowledgeProcessingRunStatus.CANCELLED):
        reason = processing.error_message
        if processing.error_code and reason:
            reason = _with_code(processing.error_code, reason)
        return {"indexing_status": "FAILED", "status_reason": reason}
    return {"indexing_status": "INDEXING", "status_reason": None}


def map_document_response(
    document: Document,
) -> DocumentResponse:

    version = _get_current_version(document)

    return DocumentResponse(
        document_id=document.document_id,
        project_id=document.project_id,
        original_filename=document.original_filename,
        extension=(
            version.file_extension or ""
        ),
        mime_type=version.mime_type,
        size_bytes=version.file_size,
        status=document.status,
        **_indexing_state(document, version),
        created_at=document.created_at,
    )


def map_document_detail_response(
    document: Document,
) -> DocumentDetailResponse:

    version = _get_current_version(document)

    return DocumentDetailResponse(
        document_id=document.document_id,
        upload_id=document.upload_id,
        project_id=document.project_id,
        original_filename=document.original_filename,
        extension=(
            version.file_extension or ""
        ),
        mime_type=version.mime_type,
        size_bytes=version.file_size,
        checksum=version.sha256_hash,
        status=document.status,
        **_indexing_state(document, version),
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def map_upload_history_response(
    upload_job: UploadJob,
) -> UploadHistoryResponse:

    return UploadHistoryResponse(
        upload_id=upload_job.upload_id,
        project_id=upload_job.project_id,
        status=upload_job.status,
        total_files=upload_job.total_files,
        processed_files=upload_job.processed_files,
        failed_files=upload_job.failed_files,
        created_at=upload_job.created_at,
    )


def map_upload_detail_response(
    upload_job: UploadJob,
    documents: list[Document],
) -> UploadDetailResponse:

    return UploadDetailResponse(
        upload=map_upload_history_response(
            upload_job
        ),
        documents=[
            map_document_response(document)
            for document in documents
        ],
    )