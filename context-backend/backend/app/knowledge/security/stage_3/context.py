from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ValidationContext:
    """
    Stage 3 - Format-Specific Security Validation Context

    Purpose:
        Shared execution context passed across every validation
        check inside Stage 3.

    This context only stores information required for
    format-specific security validation.

    It intentionally does NOT contain parser runtime objects
    or parsed document data.
    """

    # Document Identity

    document_id: str

    project_id: str

    upload_id: str | None

    parent_document_id: str | None

    original_filename: str

    file_path: Path

    extension: str

    mime_type: str

    file_size: int

    sha256: str

    # Stage Execution

    stage: str = "stage_3"

    status: str = "pending"

    current_phase: str | None = None

    current_check: str | None = None

    # Format Information

    detected_format: str | None = None

    format_family: str | None = None

    format_version: str | None = None

    version_detected: bool = False

    # Validator Information

    validator_name: str | None = None

    validator_selected: bool = False

    # Validation Results

    format_identified: bool = False

    security_validated: bool = False

    ready_for_sandbox: bool = False

    rejected: bool = False

    rejection_reason: str | None = None

    rejection_code: str | None = None

    # Findings

    findings: list[Any] = field(default_factory=list)

    warnings: list[Any] = field(default_factory=list)

    # Audit

    started_at: datetime = field(default_factory=datetime.utcnow)

    completed_at: datetime | None = None

    duration_ms: float | None = None

    # Metadata

    metadata: dict[str, Any] = field(default_factory=dict)