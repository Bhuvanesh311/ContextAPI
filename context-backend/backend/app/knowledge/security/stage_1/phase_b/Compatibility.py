from app.knowledge.security.stage_1.context import ValidationContext
from app.knowledge.security.stage_1.exceptions import (
    MimeSignatureMismatchError,
)



# Extension -> acceptable MIME types


# Shared MIME groups for the document / image formats below.
_ZIP_MIMES = frozenset({"application/zip", "application/x-zip", "application/x-zip-compressed", "application/octet-stream"})
_OLE_MIMES = frozenset({"application/x-ole-storage", "application/cdfv2", "application/vnd.ms-office", "application/octet-stream"})
_HTML_MIMES = frozenset({"text/html", "application/xhtml+xml", "text/xml", "text/plain"})
# Source files: libmagic reports text/plain or a language-specific text/x-* type,
# and often the wrong language (Java with generics reads as text/x-c++).
_TEXT_MIMES = frozenset({
    "text/plain", "text/x-c", "text/x-c++", "text/x-shellscript", "application/x-shellscript",
    "text/x-ruby", "text/x-script.python", "text/x-java", "text/x-lua", "text/javascript",
    "application/javascript", "text/x-asm", "text/x-makefile", "text/x-objective-c",
})


EXTENSION_MIME_MAP: dict[str, frozenset[str]] = {

    # -----------------------------------------------------------------------
    # Documents
    # -----------------------------------------------------------------------

    ".pdf": frozenset({
        "application/pdf",
    }),

    ".docx": frozenset({
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/x-zip",
        "application/x-zip-compressed",
    }),

    ".txt": frozenset({
        "text/plain",
    }),

    ".md": frozenset({
        "text/plain",
        "text/markdown",
    }),

    # -----------------------------------------------------------------------
    # API / Structured Data
    # -----------------------------------------------------------------------

    ".json": frozenset({
        "application/json",
        "text/json",
        "text/plain",
    }),

    ".yaml": frozenset({
        "application/yaml",
        "application/x-yaml",
        "text/yaml",
        "text/x-yaml",
        "text/plain",
    }),

    ".yml": frozenset({
        "application/yaml",
        "application/x-yaml",
        "text/yaml",
        "text/x-yaml",
        "text/plain",
    }),

    ".xml": frozenset({
        "application/xml",
        "text/xml",
        "text/plain",
    }),

    ".csv": frozenset({
        "text/csv",
        "text/plain",
    }),

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

    ".ini": frozenset({
        "text/plain",
    }),

    ".conf": frozenset({
        "text/plain",
    }),

    ".cfg": frozenset({
        "text/plain",
    }),

    ".properties": frozenset({
        "text/plain",
    }),

    ".toml": frozenset({
        "text/plain",
        "application/toml",
    }),

    # -----------------------------------------------------------------------
    # Logs
    # -----------------------------------------------------------------------

    ".log": frozenset({
        "text/plain",
    }),

    # -----------------------------------------------------------------------
    # Source Code
    # -----------------------------------------------------------------------

    ".py": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-python",
        "text/x-script.python",
    }),

    ".js": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/javascript",
        "application/javascript",
    }),

    ".ts": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/typescript",
        "application/typescript",
    }),

    ".java": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-java",
        "text/x-java-source",
    }),

    ".go": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-go",
    }),

    ".cs": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-csharp",
    }),

    ".php": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-php",
        "application/x-php",
    }),

    ".c": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-c",
    }),

    ".cpp": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-c++",
        "text/x-c++src",
    }),

    ".rs": _TEXT_MIMES | frozenset({
        "text/plain",
        "text/x-rust",
    }),

    ".sql": _TEXT_MIMES | frozenset({
        "text/plain",
        "application/sql",
        "text/x-sql",
    }),

    # -----------------------------------------------------------------------
    # More documents: Office, OpenDocument, RTF, HTML, images
    # -----------------------------------------------------------------------

    ".pptx": _ZIP_MIMES | {"application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    ".xlsx": _ZIP_MIMES | {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".doc": _OLE_MIMES | {"application/msword", "text/rtf", "application/rtf"},
    ".xls": _OLE_MIMES | {"application/vnd.ms-excel"},
    ".ppt": _OLE_MIMES | {"application/vnd.ms-powerpoint"},
    ".rtf": frozenset({"text/rtf", "application/rtf", "text/plain"}),
    ".odt": _ZIP_MIMES | {"application/vnd.oasis.opendocument.text"},
    ".ods": _ZIP_MIMES | {"application/vnd.oasis.opendocument.spreadsheet"},
    ".odp": _ZIP_MIMES | {"application/vnd.oasis.opendocument.presentation"},
    ".html": _HTML_MIMES,
    ".htm": _HTML_MIMES,
    ".png": frozenset({"image/png"}),
    ".jpg": frozenset({"image/jpeg"}),
    ".jpeg": frozenset({"image/jpeg"}),
    ".bmp": frozenset({"image/bmp", "image/x-ms-bmp"}),
    ".tif": frozenset({"image/tiff"}),
    ".tiff": frozenset({"image/tiff"}),
    ".webp": frozenset({"image/webp"}),

    # Plain-text documents and more source code (libmagic usually says
    # text/plain, sometimes a language-specific text/x-* type).
    ".rst": _TEXT_MIMES,
    ".tsv": _TEXT_MIMES | {"text/tab-separated-values"},
    ".jsx": _TEXT_MIMES,
    ".tsx": _TEXT_MIMES,
    ".h": _TEXT_MIMES,
    ".hpp": _TEXT_MIMES,
    ".cc": _TEXT_MIMES,
    ".cxx": _TEXT_MIMES,
    ".hh": _TEXT_MIMES,
    ".rb": _TEXT_MIMES,
    ".swift": _TEXT_MIMES,
    ".kt": _TEXT_MIMES,
    ".kts": _TEXT_MIMES,
    ".scala": _TEXT_MIMES,
    ".sh": _TEXT_MIMES,
    ".bash": _TEXT_MIMES,
    ".lua": _TEXT_MIMES,
    ".r": _TEXT_MIMES,
    ".dart": _TEXT_MIMES,
    ".vb": _TEXT_MIMES,

    # -----------------------------------------------------------------------
    # Archives
    # -----------------------------------------------------------------------

    ".zip": frozenset({
        "application/zip",
        "application/x-zip",
        "application/x-zip-compressed",
    }),

    ".tar": frozenset({
        "application/x-tar",
        "application/tar",
    }),

    # Important:
    # libmagic sees the OUTER gzip layer here.
    # Stage 2 must verify that the decompressed payload is actually TAR.
    ".tar.gz": frozenset({
        "application/gzip",
        "application/x-gzip",
    }),

    ".tgz": frozenset({
        "application/gzip",
        "application/x-gzip",
    }),
}



# Generic / inconclusive MIME types


INCONCLUSIVE_MIME_TYPES: frozenset[str] = frozenset({
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-binary",
})



# Explicit executable/native binary MIME types


DANGEROUS_MIME_TYPES: frozenset[str] = frozenset({
    "application/x-dosexec",
    "application/x-msdownload",
    "application/x-msdos-program",
    "application/vnd.microsoft.portable-executable",
    "application/x-executable",
    "application/x-pie-executable",
    "application/x-sharedlib",
})



# Helpers


def _normalize_extension(extension: str) -> str:
    """
    Normalize the extension supplied by ValidationContext.

    Compound extensions such as '.tar.gz' must already have been
    resolved by the file-identity layer. This function intentionally
    does not attempt to infer them from the filename.
    """

    return extension.lower().strip()


def _normalize_mime_type(mime_type: str) -> str:
    """
    Normalize MIME values before policy comparison.

    Example:
        application/gzip; charset=binary
        ->
        application/gzip
    """

    return mime_type.lower().strip().split(";", 1)[0].strip()



# Compatibility validation


def validate_file_compatibility(
    context: ValidationContext,
) -> None:
    """
    Validate Stage 1 consistency between:

    - resolved file extension
    - detected MIME type
    - magic-signature result

    This is a shallow identity/compatibility check.

    It does NOT perform archive structural validation or prove that a
    gzip stream contains TAR. Those responsibilities belong to Stage 2.

    Generic binary MIME values are considered inconclusive only when
    no explicit signature contradiction has already been discovered.
    """

    extension = context.extension
    detected_mime = context.detected_mime

    # -----------------------------------------------------------------------
    # 1. Required evidence
    # -----------------------------------------------------------------------

    if not extension:
        context.mime_signature_match = False

        raise MimeSignatureMismatchError(
            (
                "File extension is unavailable for "
                f"'{context.original_filename}'."
            ),
            phase="integrity_trust",
            check="mime_signature_matching",
            code="EXTENSION_UNAVAILABLE",
        )

    if not detected_mime:
        context.mime_signature_match = False

        raise MimeSignatureMismatchError(
            (
                "Detected MIME type is unavailable for "
                f"'{context.original_filename}'."
            ),
            phase="integrity_trust",
            check="mime_signature_matching",
            code="DETECTED_MIME_UNAVAILABLE",
        )

    extension = _normalize_extension(extension)
    detected_mime = _normalize_mime_type(detected_mime)

    # -----------------------------------------------------------------------
    # 2. Supported-extension / MIME policy
    # -----------------------------------------------------------------------

    expected_mime_types = EXTENSION_MIME_MAP.get(extension)

    if expected_mime_types is None:
        context.mime_signature_match = False

        raise MimeSignatureMismatchError(
            (
                "No MIME compatibility policy exists for "
                f"extension '{extension}'."
            ),
            phase="integrity_trust",
            check="mime_signature_matching",
            code="MIME_POLICY_UNAVAILABLE",
        )

    # -----------------------------------------------------------------------
    # 3. Explicit signature contradiction
    # -----------------------------------------------------------------------

    if context.signature_valid is False:
        context.mime_signature_match = False

        raise MimeSignatureMismatchError(
            (
                "File signature is inconsistent with "
                f"'{context.original_filename}'."
            ),
            phase="integrity_trust",
            check="mime_signature_matching",
            code="MIME_SIGNATURE_MISMATCH",
        )

    # -----------------------------------------------------------------------
    # 4. Explicit executable/native binary MIME
    # -----------------------------------------------------------------------

    if detected_mime in DANGEROUS_MIME_TYPES:
        context.mime_signature_match = False

        raise MimeSignatureMismatchError(
            (
                f"Unsafe executable MIME type '{detected_mime}' "
                f"detected for '{context.original_filename}'."
            ),
            phase="integrity_trust",
            check="mime_signature_matching",
            code="DANGEROUS_MIME_TYPE",
        )

    # -----------------------------------------------------------------------
    # 5. Inconclusive MIME
    # -----------------------------------------------------------------------

    if detected_mime in INCONCLUSIVE_MIME_TYPES:
        context.mime_signature_match = True
        return

    # -----------------------------------------------------------------------
    # 6. Known compatible MIME
    # -----------------------------------------------------------------------

    if detected_mime in expected_mime_types:
        context.mime_signature_match = True
        return

    # -----------------------------------------------------------------------
    # 7. Known MIME contradicts extension
    # -----------------------------------------------------------------------

    context.mime_signature_match = False

    raise MimeSignatureMismatchError(
        (
            f"Detected MIME type '{detected_mime}' is not "
            f"compatible with extension '{extension}' for "
            f"'{context.original_filename}'."
        ),
        phase="integrity_trust",
        check="mime_signature_matching",
        code="MIME_EXTENSION_MISMATCH",
    )