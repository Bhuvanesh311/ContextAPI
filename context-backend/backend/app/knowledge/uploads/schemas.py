from datetime import datetime
from typing import Literal

from pydantic import (BaseModel, Field, ConfigDict)
from app.core.enums import (UploadStatus, DocumentStatus)


class UploadRequest(BaseModel):
    project_id: str = Field(
        ...,
        description="Project ID where the uploaded files belong."
    )

class UploadResponse(BaseModel):
    upload_id: str = Field(
        ...,
        description="Unique upload job identifier."
    )

    total_files: int = Field(
        ...,
        ge=1,
        description="Total number of uploaded files."
    )


class UploadStatusResponse(BaseModel):
    upload_id: str = Field(
        ...,
        description="Upload job identifier."
    )

    status: UploadStatus = Field(
        ...,
        description="Current upload status."
    )

    total_files: int = Field(
        ...,
        ge=0
    )

    processed_files: int = Field(
        ...,
        ge=0
    )

    failed_files: int = Field(
        ...,
        ge=0
    )

    remaining_files: int = Field(
        ...,
        ge=0
    )


class PaginationQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    search: str | None = None

    project_id: str | None = None

    status: DocumentStatus | None = None

    sort_by: str = "created_at"

    order: Literal["asc", "desc"] = "desc"



class PaginationMeta(BaseModel):
    page: int

    page_size: int

    total_records: int

    total_pages: int

    has_next: bool

    has_previous: bool

class DocumentResponse(BaseModel):

    document_id: str
    project_id: str
    original_filename: str
    extension: str
    mime_type: str
    size_bytes: int
    status: DocumentStatus
    indexing_status: str = Field(
        default="UNKNOWN",
        description="INGESTING / INDEXING / READY (searchable) / REJECTED / FAILED / CANCELLED (stopped by user)",
    )
    status_reason: str | None = Field(
        default=None,
        description="Why the document was rejected or failed.",
    )
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )
class DocumentDetailResponse(BaseModel):

    document_id: str
    upload_id: str
    project_id: str
    original_filename: str
    extension: str
    mime_type: str
    size_bytes: int
    checksum: str
    status: DocumentStatus
    indexing_status: str = Field(
        default="UNKNOWN",
        description="INGESTING / INDEXING / READY (searchable) / REJECTED / FAILED / CANCELLED (stopped by user)",
    )
    status_reason: str | None = Field(
        default=None,
        description="Why the document was rejected or failed.",
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )
class DocumentListResponse(BaseModel):

    documents: list[DocumentResponse]

    pagination: PaginationMeta


class UploadHistoryResponse(BaseModel):

    upload_id: str

    project_id: str

    status: UploadStatus

    total_files: int

    processed_files: int

    failed_files: int

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UploadDetailResponse(BaseModel):

    upload: UploadHistoryResponse

    documents: list[DocumentResponse]

class PaginatedUploadResponse(BaseModel):

    uploads: list[UploadHistoryResponse]

    pagination: PaginationMeta


class UpdateDocumentRequest(BaseModel):
    original_filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Updated display name of the document.",
    )