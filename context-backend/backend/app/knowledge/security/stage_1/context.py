from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.knowledge.security.stage_1.constants import (
    FILE_TYPE_UNKNOWN,
    STATUS_PENDING,
)


@dataclass
class ValidationContext:
 
    # Identity

    upload_id: str
    project_id: str
    document_id: str
    file_path: Path
    original_filename: str

    # Basic File Metadata

    extension: str | None = None
    file_size: int | None = None

    created_at: datetime | None = None
    modified_at: datetime | None = None

    # MIME / Signature

    declared_mime: str | None = None
    detected_mime: str | None = None

    signature_valid: bool | None = None
    mime_signature_match: bool | None = None

    # Integrity

    sha256: str | None = None

    duplicate: bool | None = None
    duplicate_document_id: str | None = None

    # Content Classification

    content_type: str = FILE_TYPE_UNKNOWN

    encoding: str | None = None
    encoding_confidence: float | None = None

    # Entropy

    entropy: float | None = None
    entropy_classification: str | None = None

    # Malware

    malware_status: str | None = None
    malware_name: str | None = None

    # Storage Verification

    storage_status: str | None = None

    storage_exists: bool | None = None
    storage_readable: bool | None = None

    storage_size_match: bool | None = None
    storage_hash_match: bool | None = None

    # Stage State

    status: str = STATUS_PENDING

    current_phase: str | None = None
    current_check: str | None = None

    failure_code: str | None = None
    failure_reason: str | None = None

    # Timing

    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Additional Results

    metadata: dict[str, Any] = field(default_factory=dict)