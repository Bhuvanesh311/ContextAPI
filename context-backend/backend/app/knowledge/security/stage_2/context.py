from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.knowledge.security.stage_2.constants import (
    ArchiveType,
    CONTEXT_PENDING,
)



# Archive Entry

@dataclass(slots=True)
class ArchiveEntry:
    """
    Normalized metadata describing one entry inside an archive.

    ZIP/TAR/7Z/RAR expose different metadata APIs. Stage 2
    converts them into this common representation so Phase B
    does not need archive-library-specific logic everywhere.
    """

    name: str

    compressed_size: int = 0
    uncompressed_size: int = 0

    compression_method: str | None = None

    is_directory: bool = False
    is_file: bool = True

    is_symlink: bool = False
    is_hardlink: bool = False

    is_encrypted: bool = False

    # Set later when archive/format detection determines that
    # this child itself represents another user archive.
    is_archive: bool = False

    detected_archive_type: ArchiveType | None = None

    # Optional archive-library-specific information.
    metadata: dict[str, Any] = field(
        default_factory=dict
    )



# Extracted Child

@dataclass(slots=True)
class ExtractedFile:
    """
    Represents a safely materialized archive child.

    Phase D can later use this information to create the
    corresponding Document record.
    """

    original_entry_name: str

    file_path: Path

    size: int

    is_archive: bool = False

    archive_type: ArchiveType | None = None

    document_id: str | None = None



# Stage 2 Context

@dataclass(slots=True)
class ArchiveValidationContext:
    """
    Mutable state passed through the complete Stage 2 archive
    validation pipeline.
    """

    
    # Document identity
    

    document_id: str
    upload_id: str
    project_id: str

    original_filename: str
    file_path: Path

    
    # Archive hierarchy
    

    parent_document_id: str | None = None

    archive_depth: int = 0

    
    # Evidence inherited from Stage 1
    

    detected_mime: str | None = None

    checksum: str | None = None

    
    # Phase A - Identity & Metadata
    

    archive_type: ArchiveType | None = None

    format_valid: bool | None = None

    entries: list[ArchiveEntry] = field(
        default_factory=list
    )

    entry_count: int = 0

    compressed_size: int = 0

    estimated_extracted_size: int = 0

    compression_ratio: float | None = None

    compression_methods: set[str] = field(
        default_factory=set
    )

    
    # Phase B - Security
    

    integrity_valid: bool | None = None

    encrypted: bool = False

    password_protected: bool = False

    contains_symlinks: bool = False

    contains_hardlinks: bool = False

    contains_nested_archives: bool = False

    nested_archive_count: int = 0

    duplicate_entries: list[str] = field(
        default_factory=list
    )

    
    # Phase C - Controlled Extraction
    

    extraction_workspace: Path | None = None

    extracted_paths: list[Path] = field(
        default_factory=list
    )

    extracted_files: list[Any] = field(
        default_factory=list
    )

    # Members left out on purpose (VCS data, caches, build output).
    skipped_entries: list[str] = field(
        default_factory=list
    )

    extraction_report: dict[str, Any] | None = None
    
    # Phase D - Child Orchestration
    

    child_document_ids: list[str] = field(
        default_factory=list
    )

    
    # Pipeline State
    

    current_phase: str | None = None

    current_check: str | None = None

    status: str = CONTEXT_PENDING

    
    # Helper Methods
    

    def add_entry(
        self,
        entry: ArchiveEntry,
    ) -> None:
        self.entries.append(entry)

    def add_extracted_file(
        self,
        extracted_file: ExtractedFile,
    ) -> None:
        self.extracted_files.append(
            extracted_file
        )

    def add_child_document(
        self,
        document_id: str,
    ) -> None:
        self.child_document_ids.append(
            document_id
        )