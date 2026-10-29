from __future__ import annotations

from app.core.enums import FileCategory
from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    FormatIdentificationError,
)


FORMAT_CATEGORY_MAP: dict[str, tuple[str, FileCategory]] = {
    # Documentation
    ".pdf": ("pdf", FileCategory.PDF),
    ".docx": ("docx", FileCategory.OFFICE),

    # Structured
    ".json": ("json", FileCategory.STRUCTURED),
    ".xml": ("xml", FileCategory.STRUCTURED),
    ".yaml": ("yaml", FileCategory.STRUCTURED),
    ".yml": ("yaml", FileCategory.STRUCTURED),

    # Text
    ".txt": ("text", FileCategory.TEXT),
    ".md": ("markdown", FileCategory.TEXT),
    ".log": ("log", FileCategory.TEXT),
    ".csv": ("csv", FileCategory.TEXT),
    ".sql": ("sql", FileCategory.TEXT),

    # Configuration
    ".ini": ("ini", FileCategory.CONFIGURATION),
    ".cfg": ("cfg", FileCategory.CONFIGURATION),
    ".conf": ("conf", FileCategory.CONFIGURATION),
    ".properties": ("properties", FileCategory.CONFIGURATION),
    ".toml": ("toml", FileCategory.CONFIGURATION),

    # Source Code
    ".py": ("python", FileCategory.SOURCE_CODE),
    ".js": ("javascript", FileCategory.SOURCE_CODE),
    ".ts": ("typescript", FileCategory.SOURCE_CODE),
    ".java": ("java", FileCategory.SOURCE_CODE),
    ".go": ("go", FileCategory.SOURCE_CODE),
    ".cs": ("csharp", FileCategory.SOURCE_CODE),
    ".php": ("php", FileCategory.SOURCE_CODE),
    ".c": ("c", FileCategory.SOURCE_CODE),
    ".cpp": ("cpp", FileCategory.SOURCE_CODE),
    ".rs": ("rust", FileCategory.SOURCE_CODE),
    ".jsx": ("source_code", FileCategory.SOURCE_CODE),
    ".tsx": ("source_code", FileCategory.SOURCE_CODE),
    ".h": ("source_code", FileCategory.SOURCE_CODE),
    ".hpp": ("source_code", FileCategory.SOURCE_CODE),
    ".cc": ("source_code", FileCategory.SOURCE_CODE),
    ".cxx": ("source_code", FileCategory.SOURCE_CODE),
    ".hh": ("source_code", FileCategory.SOURCE_CODE),
    ".rb": ("source_code", FileCategory.SOURCE_CODE),
    ".swift": ("source_code", FileCategory.SOURCE_CODE),
    ".kt": ("source_code", FileCategory.SOURCE_CODE),
    ".kts": ("source_code", FileCategory.SOURCE_CODE),
    ".scala": ("source_code", FileCategory.SOURCE_CODE),
    ".sh": ("source_code", FileCategory.SOURCE_CODE),
    ".bash": ("source_code", FileCategory.SOURCE_CODE),
    ".lua": ("source_code", FileCategory.SOURCE_CODE),
    ".r": ("source_code", FileCategory.SOURCE_CODE),
    ".dart": ("source_code", FileCategory.SOURCE_CODE),
    ".vb": ("source_code", FileCategory.SOURCE_CODE),

    # Office / OpenDocument / RTF
    ".pptx": ("pptx", FileCategory.OFFICE),
    ".xlsx": ("xlsx", FileCategory.OFFICE),
    ".doc": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".xls": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".ppt": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".rtf": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".odt": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".ods": ("legacy_office", FileCategory.LEGACY_OFFICE),
    ".odp": ("legacy_office", FileCategory.LEGACY_OFFICE),

    # Web pages and plain-text documents
    ".html": ("html", FileCategory.TEXT),
    ".htm": ("html", FileCategory.TEXT),
    ".rst": ("text", FileCategory.TEXT),
    ".tsv": ("text", FileCategory.TEXT),

    # Images (read with OCR)
    ".png": ("image", FileCategory.IMAGE),
    ".jpg": ("image", FileCategory.IMAGE),
    ".jpeg": ("image", FileCategory.IMAGE),
    ".bmp": ("image", FileCategory.IMAGE),
    ".tif": ("image", FileCategory.IMAGE),
    ".tiff": ("image", FileCategory.IMAGE),
    ".webp": ("image", FileCategory.IMAGE),
}


def identify_document_format(
    context: ValidationContext,
) -> None:
    """
    Phase A

    Identify the canonical document format and assign the
    internal format family used by Stage 3 validators.

    Stage 1 has already validated:
        - Extension
        - MIME
        - Magic Signature

    Therefore this function performs classification only.
    """

    extension = context.extension.lower()

    mapping = FORMAT_CATEGORY_MAP.get(
        extension,
    )

    if mapping is None:
        raise FormatIdentificationError(
            f"Unsupported format '{extension}'.",
            phase="format_identification",
            check="format_detection",
            code="UNSUPPORTED_FORMAT",
        )

    detected_format, category = mapping

    context.detected_format = detected_format
    context.format_family = category.value

    context.format_identified = True

    context.metadata["detected_format"] = detected_format
    context.metadata["format_family"] = category.value