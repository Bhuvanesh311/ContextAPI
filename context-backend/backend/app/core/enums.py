from enum import Enum


# Project

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    PENDING = "pending"


class EnvironmentEnum(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"
    SANDBOX = "sandbox"


# Upload

class UploadStatus(str, Enum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Document

class DocumentStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    # Ingestion outcomes: never indexed, never searched.
    REJECTED = "REJECTED"   # failed a security / format check (permanent)
    FAILED = "FAILED"       # ingestion error after all retries


# Document Version

class DocumentVersionStatus(str, Enum):
    CREATED = "CREATED"
    QUARANTINED = "QUARANTINED"
    PROCESSING = "PROCESSING"
    VALIDATED = "VALIDATED"
    READY_FOR_PROCESSING = "READY_FOR_PROCESSING"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Ingestion Run

class IngestionRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class IngestionStage(str, Enum):
    UPLOAD_RECEIVED = "UPLOAD_RECEIVED"

    QUARANTINE_STORAGE = "QUARANTINE_STORAGE"

    PRE_SECURITY_VALIDATION = "PRE_SECURITY_VALIDATION"

    FORMAT_IDENTIFICATION = "FORMAT_IDENTIFICATION"
    FORMAT_VALIDATION = "FORMAT_VALIDATION"

    PARSER_SELECTION = "PARSER_SELECTION"
    SANDBOXED_PARSING = "SANDBOXED_PARSING"

    POST_PARSE_VALIDATION = "POST_PARSE_VALIDATION"

    AI_RAG_SECURITY_VALIDATION = "AI_RAG_SECURITY_VALIDATION"

    PERMANENT_STORAGE = "PERMANENT_STORAGE"

    CLEANUP = "CLEANUP"

    COMPLETED = "COMPLETED"


# Knowledge Processing

class KnowledgeProcessingRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class KnowledgeProcessingStage(str, Enum):
    INITIALIZATION = "INITIALIZATION"

    SOURCE_VALIDATION = "SOURCE_VALIDATION"

    CHUNKING = "CHUNKING"
    CHUNK_VALIDATION = "CHUNK_VALIDATION"

    EMBEDDING = "EMBEDDING"

    VECTOR_INDEXING = "VECTOR_INDEXING"
    INDEX_VALIDATION = "INDEX_VALIDATION"

    COMPLETED = "COMPLETED"


# Document Chunks

class DocumentChunkStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"


class ChunkLevel(str, Enum):
    DOCUMENT = "DOCUMENT"
    SECTION = "SECTION"
    CHUNK = "CHUNK"


# Embeddings

class EmbeddingStatus(str, Enum):
    PENDING = "PENDING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


# File Classification

class FileCategory(str, Enum):
    PDF = "PDF"
    OFFICE = "OFFICE"
    STRUCTURED = "STRUCTURED"
    TEXT = "TEXT"
    CONFIGURATION = "CONFIGURATION"
    SOURCE_CODE = "SOURCE_CODE"
    IMAGE = "IMAGE"
    LEGACY_OFFICE = "LEGACY_OFFICE"   # .doc/.xls/.ppt/.rtf/OpenDocument, converted by LibreOffice
    UNKNOWN = "UNKNOWN"

class ChunkStatus(str, Enum):
    READY_FOR_CHUNKING = "READY_FOR_CHUNKING"
    CHUNKING = "CHUNKING"
    READY_FOR_EMBEDDING = "READY_FOR_EMBEDDING"
    FAILED = "FAILED"


class ChunkType(str, Enum):
    RECURSIVE = "recursive"
    FIXED = "fixed"
    SEMANTIC = "semantic"


# Retrieval

class RequestSourceType(str, Enum):
    USER = "USER"
    PLANNER_AGENT = "PLANNER_AGENT"
    AGENT = "AGENT"
    WORKFLOW = "WORKFLOW"
    INTERNAL = "INTERNAL"


class ExecutionProfile(str, Enum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    DEEP = "DEEP"
    COLLABORATIVE = "COLLABORATIVE"


class QueryIntent(str, Enum):
    EXACT_LOOKUP = "EXACT_LOOKUP"
    METADATA_SEARCH = "METADATA_SEARCH"
    FACT_LOOKUP = "FACT_LOOKUP"
    EXPLANATION = "EXPLANATION"
    COMPARISON = "COMPARISON"
    ANALYSIS = "ANALYSIS"
    RELATIONSHIP = "RELATIONSHIP"
    INVESTIGATION = "INVESTIGATION"
    MULTI_STEP = "MULTI_STEP"
    UNKNOWN = "UNKNOWN"


class QueryComplexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class RetrievalRequestStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RetrievalRequirementType(str, Enum):
    SEMANTIC = "SEMANTIC"
    LEXICAL = "LEXICAL"
    EXACT = "EXACT"
    RELATIONAL = "RELATIONAL"
    HYBRID = "HYBRID"


class QuerySafetyOutcome(str, Enum):
    SAFE = "SAFE"
    BLOCKED = "BLOCKED"


class MemoryRequirement(str, Enum):
    NONE = "NONE"
    SESSION = "SESSION"
    LONG_TERM = "LONG_TERM"
    WORKFLOW = "WORKFLOW"


class AnalysisMethod(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    SEMANTIC_ROUTING = "SEMANTIC_ROUTING"    # Tier B: local SLM
    LLM_AUGMENTED = "LLM_AUGMENTED"         # Tier C: external LLM