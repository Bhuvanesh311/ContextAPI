from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    String, Integer, BigInteger, DateTime, ForeignKey, Text, JSON,
    UniqueConstraint, Index, Computed,
)
from sqlalchemy.dialects.postgresql import TSVECTOR

from sqlalchemy import (
    String,
    Integer,
    BigInteger,
    DateTime,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy import Enum as SqlEnum

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.core.database import Base
from app.core.enums import (
    UploadStatus,
    DocumentStatus,
    DocumentVersionStatus,
    IngestionRunStatus,
    IngestionStage,
    KnowledgeProcessingRunStatus,
    KnowledgeProcessingStage,
    DocumentChunkStatus,
    ChunkLevel,
    EmbeddingStatus,
)


if TYPE_CHECKING:
    from app.auth.models import User
    from app.project.models import Project


# upload jobs

class UploadJob(Base):
    __tablename__ = "upload_jobs"

    upload_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
        index=True,
    )

    status: Mapped[UploadStatus] = mapped_column(
        SqlEnum(UploadStatus),
        nullable=False,
        default=UploadStatus.QUEUED,
    )

    total_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    processed_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    failed_files: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="upload_jobs",
    )

    project = relationship(
        "Project",
        back_populates="upload_jobs",
    )

    documents = relationship(
        "Document",
        back_populates="upload_job",
    )


Index(
    "idx_upload_status",
    UploadJob.status,
)


# documents

class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    upload_id: Mapped[str | None] = mapped_column(
        ForeignKey("upload_jobs.upload_id"),
        nullable=True,
        index=True,
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.project_id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
        index=True,
    )

    parent_document_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "documents.document_id",
            ondelete="CASCADE",
        ),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    status: Mapped[DocumentStatus] = mapped_column(
        SqlEnum(DocumentStatus),
        nullable=False,
        default=DocumentStatus.ACTIVE,
    )

    current_version_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "document_versions.document_version_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship(
        "User",
        back_populates="documents",
    )

    project = relationship(
        "Project",
        back_populates="documents",
    )

    upload_job = relationship(
        "UploadJob",
        back_populates="documents",
    )

    current_version = relationship(
        "DocumentVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )

    versions = relationship(
        "DocumentVersion",
        foreign_keys="DocumentVersion.document_id",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    ingestion_runs = relationship(
        "IngestionRun",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    parent_document = relationship(
        "Document",
        remote_side=[document_id],
        foreign_keys=[parent_document_id],
        back_populates="child_documents",
    )

    child_documents = relationship(
        "Document",
        foreign_keys=[parent_document_id],
        back_populates="parent_document",
        cascade="all, delete-orphan",
        single_parent=True,
    )


Index(
    "idx_document_status",
    Document.status,
)

Index(
    "idx_document_project",
    Document.project_id,
)

Index(
    "idx_document_user",
    Document.user_id,
)

Index(
    "idx_document_parent",
    Document.parent_document_id,
)

Index(
    "idx_document_current_version",
    Document.current_version_id,
)


# document versions

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    document_version_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey(
            "documents.document_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    file_extension: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    sha256_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    source_reference: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    quarantine_bucket: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    quarantine_object_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    permanent_bucket: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    permanent_object_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    parsed_bucket: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    parsed_object_key: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    parsed_format: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    status: Mapped[DocumentVersionStatus] = mapped_column(
        SqlEnum(DocumentVersionStatus),
        nullable=False,
        default=DocumentVersionStatus.CREATED,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    document = relationship(
        "Document",
        foreign_keys=[document_id],
        back_populates="versions",
    )

    ingestion_runs = relationship(
        "IngestionRun",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    knowledge_processing_runs = relationship(
        "KnowledgeProcessingRun",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    chunks = relationship(
        "DocumentChunk",
        back_populates="document_version",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version_number",
            name="uq_document_version_number",
        ),
    )


Index(
    "idx_document_version_status",
    DocumentVersion.status,
)

Index(
    "idx_document_version_sha256",
    DocumentVersion.sha256_hash,
)


# ingestion runs

class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    ingestion_run_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    document_id: Mapped[str] = mapped_column(
        ForeignKey(
            "documents.document_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    document_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_versions.document_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[IngestionRunStatus] = mapped_column(
        SqlEnum(IngestionRunStatus),
        nullable=False,
        default=IngestionRunStatus.PENDING,
    )

    current_stage: Mapped[IngestionStage] = mapped_column(
        SqlEnum(IngestionStage),
        nullable=False,
        default=IngestionStage.UPLOAD_RECEIVED,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    checkpoint_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    failed_stage: Mapped[IngestionStage | None] = mapped_column(
        SqlEnum(IngestionStage),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    document = relationship(
        "Document",
        back_populates="ingestion_runs",
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="ingestion_runs",
    )


Index(
    "idx_ingestion_run_status",
    IngestionRun.status,
)

Index(
    "idx_ingestion_run_stage",
    IngestionRun.current_stage,
)

Index(
    "idx_ingestion_run_retry",
    IngestionRun.status,
    IngestionRun.next_retry_at,
)

Index(
    "idx_ingestion_run_version",
    IngestionRun.document_version_id,
)


# knowledge processing runs

class KnowledgeProcessingRun(Base):
    __tablename__ = "knowledge_processing_runs"

    knowledge_processing_run_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    document_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_versions.document_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[KnowledgeProcessingRunStatus] = mapped_column(
        SqlEnum(KnowledgeProcessingRunStatus),
        nullable=False,
        default=KnowledgeProcessingRunStatus.PENDING,
    )

    current_stage: Mapped[KnowledgeProcessingStage] = mapped_column(
        SqlEnum(KnowledgeProcessingStage),
        nullable=False,
        default=KnowledgeProcessingStage.INITIALIZATION,
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    checkpoint_data: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    failed_stage: Mapped[KnowledgeProcessingStage | None] = mapped_column(
        SqlEnum(KnowledgeProcessingStage),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    error_details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="knowledge_processing_runs",
    )


Index(
    "idx_kpr_status",
    KnowledgeProcessingRun.status,
)

Index(
    "idx_kpr_stage",
    KnowledgeProcessingRun.current_stage,
)

Index(
    "idx_kpr_retry",
    KnowledgeProcessingRun.status,
    KnowledgeProcessingRun.next_retry_at,
)

Index(
    "idx_kpr_version",
    KnowledgeProcessingRun.document_version_id,
)


# document chunks

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    chunk_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    document_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_versions.document_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    parent_chunk_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "document_chunks.chunk_id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    chunk_level: Mapped[ChunkLevel] = mapped_column(
        SqlEnum(ChunkLevel),
        nullable=False,
    )

    status: Mapped[DocumentChunkStatus] = mapped_column(
        SqlEnum(DocumentChunkStatus),
        nullable=False,
        default=DocumentChunkStatus.CREATED,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    token_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    source_locator: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    chunk_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    chunking_strategy: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    chunk_metadata: Mapped[dict | None] = mapped_column(
    "metadata",
    JSON,
    nullable=True,
    )

    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(content, ''))", persisted=True),
        nullable=True,
        deferred=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    document_version = relationship(
        "DocumentVersion",
        back_populates="chunks",
    )

    parent_chunk = relationship(
        "DocumentChunk",
        remote_side=[chunk_id],
        foreign_keys=[parent_chunk_id],
        back_populates="child_chunks",
    )

    child_chunks = relationship(
        "DocumentChunk",
        foreign_keys=[parent_chunk_id],
        back_populates="parent_chunk",
    )

    embeddings = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_document_version_chunk_index",
        ),
    )


Index(
    "idx_document_chunk_version",
    DocumentChunk.document_version_id,
)

Index(
    "idx_document_chunk_status",
    DocumentChunk.status,
)

# Exact-phrase (ILIKE '%...%') search in retrieval L05; needs pg_trgm.
Index(
    "ix_document_chunks_content_trgm",
    DocumentChunk.content,
    postgresql_using="gin",
    postgresql_ops={"content": "gin_trgm_ops"},
)

Index(
    "idx_document_chunks_search_vector",
    DocumentChunk.search_vector, postgresql_using="gin")

# chunk embeddings

class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    embedding_id: Mapped[str] = mapped_column(
        String(20),
        primary_key=True,
        index=True,
    )

    chunk_id: Mapped[str] = mapped_column(
        ForeignKey(
            "document_chunks.chunk_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    embedding_provider: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    embedding_model_version: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    embedding_dimension: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    vector_database: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    collection_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    vector_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    status: Mapped[EmbeddingStatus] = mapped_column(
        SqlEnum(EmbeddingStatus),
        nullable=False,
        default=EmbeddingStatus.PENDING,
    )

    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    chunk = relationship(
        "DocumentChunk",
        back_populates="embeddings",
    )


Index(
    "idx_chunk_embedding_chunk",
    ChunkEmbedding.chunk_id,
)

Index(
    "idx_chunk_embedding_status",
    ChunkEmbedding.status,
)

Index(
    "idx_chunk_embedding_content_hash",
    ChunkEmbedding.content_hash,
)

Index(
    "idx_chunk_embedding_vector",
    ChunkEmbedding.vector_database,
    ChunkEmbedding.collection_name,
    ChunkEmbedding.vector_id,
)