from __future__ import annotations

import posixpath
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree

from defusedxml import ElementTree as DefusedElementTree

from app.knowledge.security.stage_3.context import (
    ValidationContext,
)
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)


# ============================================================
# Structural Limits
# ============================================================

MAX_DOCX_SIZE = 100 * 1024 * 1024          # 100 MB
MAX_ZIP_ENTRIES = 10_000
MAX_XML_SIZE = 50 * 1024 * 1024            # 50 MB

# ============================================================
# Required OpenXML Parts
# ============================================================

REQUIRED_DOCX_PARTS = {
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
}

# Main part of each OpenXML package type.
REQUIRED_PARTS_BY_EXTENSION = {
    ".docx": REQUIRED_DOCX_PARTS,
    ".pptx": {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml"},
    ".xlsx": {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml"},
}

# ============================================================
# XML Security
# ============================================================

FORBIDDEN_XML_PATTERNS = (
    b"<!DOCTYPE",
    b"<!ENTITY",
)

# ============================================================
# Active Content
# ============================================================

VBA_PROJECT_PATH = "word/vbaProject.bin"

ACTIVEX_PATH_PREFIX = "word/activeX/"

OLE_OBJECT_PATH_PREFIX = "word/embeddings/"

# ============================================================
# Embedded Content
# ============================================================

EXECUTABLE_EXTENSIONS = {
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".com",
    ".scr",
    ".ps1",
    ".vbs",
    ".js",
    ".jar",
    ".msi",
}

PACKAGE_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".iso",
}

# ============================================================
# Archive Safety
# ============================================================

MAX_COMPRESSION_RATIO = 100

ZIP_SLIP_INDICATORS = (
    "../",
    "..\\",
    "/",
    "\\",
)

def validate(
    context: ValidationContext,
) -> None:
    """
    Perform format-specific security validation for
    Microsoft Word (DOCX) documents.
    """

    archive = _open_archive(
        context,
    )

    # ========================================================
    # Structural Validation
    # ========================================================

    _validate_structural(
        context,
        archive,
    )

    # ========================================================
    # XML Security Validation
    # ========================================================

    _validate_xml_security(
        context,
        archive,
    )

    # ========================================================
    # Active Content Validation
    # ========================================================

    _validate_active_content(
        context,
        archive,
    )

    # ========================================================
    # Embedded Content Validation
    # ========================================================

    _validate_embedded_content(
        context,
        archive,
    )

    context.security_validated = True

def _open_archive(
    context: ValidationContext,
) -> zipfile.ZipFile:
    """
    Open the DOCX archive for security validation.
    """

    try:

        return zipfile.ZipFile(
            context.file_path,
            mode="r",
        )

    except zipfile.BadZipFile as exc:

        raise FormatSecurityError(
            "Invalid DOCX archive.",
            phase="structural_validation",
            check="zip_structure",
            code="INVALID_DOCX_ARCHIVE",
        ) from exc

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to open DOCX archive.",
            phase="structural_validation",
            check="zip_structure",
            code="DOCX_OPEN_FAILED",
        ) from exc


    # ========================================================
    # Structural Validation
    # ========================================================


def _validate_structural(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate the DOCX package structure.
    """

    _validate_zip_structure(
        context,
        archive,
    )

    _validate_central_directory(
        context,
        archive,
    )

    _validate_required_parts(
        context,
        archive,
    )

    _validate_content_types(
        context,
        archive,
    )

    _validate_relationships(
        context,
        archive,
    )

def _validate_zip_structure(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate that the archive is readable.
    """

    try:

        archive.infolist()

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid ZIP structure.",
            phase="structural_validation",
            check="zip_structure",
            code="INVALID_ZIP_STRUCTURE",
        ) from exc


def _validate_central_directory(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate the ZIP central directory.
    """

    corrupted = archive.testzip()

    if corrupted is not None:

        raise FormatSecurityError(
            f"Corrupted ZIP entry: {corrupted}",
            phase="structural_validation",
            check="central_directory",
            code="CORRUPTED_ZIP_ENTRY",
        )

def _validate_required_parts(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate required OpenXML parts.
    """

    files = set(
        archive.namelist(),
    )

    extension = (context.extension or ".docx").lower()
    missing = REQUIRED_PARTS_BY_EXTENSION.get(extension, REQUIRED_DOCX_PARTS) - files

    if missing:

        raise FormatSecurityError(
            f"Missing required {extension.lstrip('.').upper()} parts: {sorted(missing)}",
            phase="structural_validation",
            check="required_parts",
            code="MISSING_REQUIRED_PARTS",
        )

def _validate_content_types(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate the presence of the content types document.
    """

    if "[Content_Types].xml" not in archive.namelist():

        raise FormatSecurityError(
            "Missing [Content_Types].xml.",
            phase="structural_validation",
            check="content_types",
            code="MISSING_CONTENT_TYPES",
        )

def _validate_relationships(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate the root relationship document.
    """

    if "_rels/.rels" not in archive.namelist():

        raise FormatSecurityError(
            "Missing root relationships document.",
            phase="structural_validation",
            check="relationships",
            code="MISSING_RELATIONSHIPS",
        )

# ========================================================
# XML Security Validation
# ========================================================

def _validate_xml_security(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate XML security.
    """

    _validate_xml_entities(
        context,
        archive,
    )

    _validate_xxe(
        context,
        archive,
    )

def _validate_xml_entities(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Reject XML documents containing ENTITY declarations.
    """

    try:

        for name in archive.namelist():

            if not name.endswith(".xml"):
                continue

            data = archive.read(name)

            if b"<!ENTITY" in data:

                raise FormatSecurityError(
                    "XML ENTITY declaration detected.",
                    phase="xml_security_validation",
                    check="xml_entities",
                    code="DOCX_XML_ENTITY_DETECTED",
                )

    except FormatSecurityError:
        raise

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to inspect XML entities.",
            phase="xml_security_validation",
            check="xml_entities",
            code="DOCX_XML_ENTITY_VALIDATION_FAILED",
        ) from exc

def _validate_xxe(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Reject XML documents containing DOCTYPE declarations.
    """

    try:

        for name in archive.namelist():

            if not name.endswith(".xml"):
                continue

            data = archive.read(name)

            if b"<!DOCTYPE" in data:

                raise FormatSecurityError(
                    "Potential XXE detected.",
                    phase="xml_security_validation",
                    check="xxe",
                    code="DOCX_XXE_DETECTED",
                )

            DefusedElementTree.fromstring(
                data,
            )

    except FormatSecurityError:
        raise

    except Exception as exc:

        raise FormatSecurityError(
            "Unsafe XML detected.",
            phase="xml_security_validation",
            check="xxe",
            code="DOCX_XML_PARSE_FAILED",
        ) from exc

# ========================================================
# Active Content Validation
# ========================================================

def _validate_active_content(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate executable Office content.
    """

    _validate_vba_project(
        context,
        archive,
    )

    _validate_macros(
        context,
        archive,
    )

    _validate_activex(
        context,
        archive,
    )

    _validate_ole_objects(
        context,
        archive,
    )

def _warn(context: ValidationContext, code: str, message: str) -> None:
    context.warnings.append({"code": code, "message": message})


# Parsing only extracts text inside a network-less sandbox; macros, ActiveX
# controls and embedded objects are never run. They are recorded as warnings
# so ordinary documents (e.g. a Word file with an Excel chart) are accepted.

def _validate_vba_project(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Covered by _validate_macros for every package type.
    """


def _validate_macros(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Note macro-enabled Office documents.
    """

    if any(name.endswith("vbaProject.bin") for name in archive.namelist()):
        _warn(context, "OFFICE_MACRO_PRESENT", "Document contains macros; they were ignored.")


def _validate_activex(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Note ActiveX controls.
    """

    if any("/activeX/" in name for name in archive.namelist()):
        _warn(context, "OFFICE_ACTIVEX_PRESENT", "Document contains ActiveX controls; they were ignored.")


def _validate_ole_objects(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Note embedded OLE objects.
    """

    if any("/embeddings/" in name for name in archive.namelist()):
        _warn(context, "OFFICE_EMBEDDED_OBJECT", "Document contains embedded objects; only its own text is used.")

# ========================================================
# Embedded Content Validation
# ========================================================


def _validate_embedded_content(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Validate embedded package content.
    """

    _validate_embedded_executables(
        context,
        archive,
    )

    _validate_embedded_packages(
        context,
        archive,
    )


def _validate_embedded_executables(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Reject embedded executable files.
    """

    for filename in archive.namelist():

        lower = filename.lower()

        if any(
            lower.endswith(ext)
            for ext in EXECUTABLE_EXTENSIONS
        ):

            raise FormatSecurityError(
                "Embedded executable detected.",
                phase="embedded_content_validation",
                check="embedded_executables",
                code="DOCX_EMBEDDED_EXECUTABLE",
            )

def _validate_embedded_packages(
    context: ValidationContext,
    archive: zipfile.ZipFile,
) -> None:
    """
    Reject embedded archive/package files.
    """

    for filename in archive.namelist():

        lower = filename.lower()

        if any(
            lower.endswith(ext)
            for ext in PACKAGE_EXTENSIONS
        ):

            raise FormatSecurityError(
                "Embedded package detected.",
                phase="embedded_content_validation",
                check="embedded_packages",
                code="DOCX_EMBEDDED_PACKAGE",
            )