"""
Stage 3 validation for legacy and OpenDocument office files:
.doc .xls .ppt (OLE2), .rtf, .odt .ods .odp (OpenDocument ZIP).

The parser sandbox converts them with LibreOffice (headless, macros
disabled, no network) and reads the converted text. This check confirms
the container format is what the extension claims and blocks archive
bombs; macros are recorded as warnings because they are never run.
"""

from __future__ import annotations

import zipfile

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import FormatSecurityError

MAX_LEGACY_OFFICE_BYTES = 100 * 1024 * 1024   # 100 MB
MAX_ODF_ENTRIES = 10_000
MAX_ODF_UNCOMPRESSED = 500 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
RTF_SIGNATURE = b"{\\rtf"

OLE_EXTENSIONS = {".doc", ".xls", ".ppt"}
ODF_MIMETYPES = {
    ".odt": b"application/vnd.oasis.opendocument.text",
    ".ods": b"application/vnd.oasis.opendocument.spreadsheet",
    ".odp": b"application/vnd.oasis.opendocument.presentation",
}


def _fail(message: str, check: str, code: str) -> None:
    raise FormatSecurityError(message, phase="legacy_office_validation", check=check, code=code)


def validate(context: ValidationContext) -> None:
    extension = (context.extension or "").lower()

    try:
        size = context.file_path.stat().st_size
        with context.file_path.open("rb") as file:
            head = file.read(4096)
    except OSError:
        _fail("Unable to read document.", "read", "LEGACY_OFFICE_READ_FAILED")

    if size > MAX_LEGACY_OFFICE_BYTES:
        _fail("Document is larger than 100 MB.", "size", "LEGACY_OFFICE_TOO_LARGE")

    if extension in OLE_EXTENSIONS:
        if not head.startswith(OLE_SIGNATURE):
            # Some ".doc" files are really RTF or HTML saved with a .doc name.
            if not head.lstrip().startswith(RTF_SIGNATURE):
                _fail("File content does not match its extension.", "signature", "INVALID_OFFICE_SIGNATURE")
        try:
            data = context.file_path.read_bytes()
        except OSError:
            _fail("Unable to read document.", "read", "LEGACY_OFFICE_READ_FAILED")
        if b"_\x00V\x00B\x00A\x00_\x00P\x00R\x00O\x00J\x00E\x00C\x00T" in data or b"Macros" in data:
            context.warnings.append({"code": "OFFICE_MACRO_PRESENT", "message": "Document contains macros; they were ignored."})

    elif extension == ".rtf":
        if not head.lstrip().startswith(RTF_SIGNATURE):
            _fail("File content does not match its extension.", "signature", "INVALID_RTF_SIGNATURE")

    elif extension in ODF_MIMETYPES:
        try:
            with zipfile.ZipFile(context.file_path) as archive:
                infos = archive.infolist()
                if len(infos) > MAX_ODF_ENTRIES:
                    _fail("Document has too many parts.", "entries", "ODF_TOO_MANY_ENTRIES")
                total = sum(info.file_size for info in infos)
                packed = sum(info.compress_size for info in infos) or 1
                if total > MAX_ODF_UNCOMPRESSED or total / packed > MAX_COMPRESSION_RATIO:
                    _fail("Document expands to an unsafe size.", "compression", "ODF_COMPRESSION_BOMB")
                for info in infos:
                    if info.filename.startswith(("/", "\\")) or ".." in info.filename.split("/"):
                        _fail("Document contains unsafe paths.", "paths", "ODF_UNSAFE_PATH")
                try:
                    mimetype = archive.read("mimetype").strip()
                except KeyError:
                    mimetype = b""
                if mimetype != ODF_MIMETYPES[extension]:
                    _fail("File content does not match its extension.", "mimetype", "INVALID_ODF_MIMETYPE")
                if any(name.lower().startswith("basic/") for name in archive.namelist()):
                    context.warnings.append({"code": "OFFICE_MACRO_PRESENT", "message": "Document contains macros; they were ignored."})
        except zipfile.BadZipFile:
            _fail("Document is not a valid OpenDocument file.", "structure", "INVALID_ODF_STRUCTURE")

    else:
        _fail(f"Unsupported legacy office extension '{extension}'.", "extension", "UNSUPPORTED_FORMAT")

    context.security_validated = True
