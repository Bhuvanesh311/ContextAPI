from __future__ import annotations

import re
import zlib
from collections import deque

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)

# ============================================================
# Structural Limits
# ============================================================

MAX_PDF_OBJECTS = 100_000
MAX_PDF_PAGES = 10_000
MAX_PDF_STREAMS = 50_000

# ============================================================
# Parser Safety Limits
# ============================================================

MAX_OBJECT_REFERENCE_DEPTH = 100
MAX_STREAM_SIZE = 100 * 1024 * 1024          # 100 MB
MAX_DECOMPRESSED_STREAM = 250 * 1024 * 1024  # 250 MB
MAX_METADATA_SIZE = 1 * 1024 * 1024          # 1 MB

# ============================================================
# Active Content
# ============================================================

DANGEROUS_ACTIONS = {
    "/JavaScript",
    "/JS",
    "/Launch",
    "/OpenAction",
    "/SubmitForm",
    "/ImportData",
    "/ResetForm",
    "/Hide",
}

# ============================================================
# Embedded Content
# ============================================================

DANGEROUS_EMBEDDED_TYPES = {
    "/EmbeddedFiles",
    "/EmbeddedFile",
    "/FileAttachment",
    "/RichMedia",
    "/Movie",
    "/Sound",
    "/3D",
    "/Flash",
}

# ============================================================
# Dangerous URI Schemes
# ============================================================

DANGEROUS_URI_SCHEMES = (
    "javascript:",
    "file:",
    "data:",
)

# ============================================================
# Dangerous Annotation Types
# ============================================================

DANGEROUS_ANNOTATIONS = {
    "/RichMedia",
    "/Movie",
    "/Screen",
    "/Sound",
    "/FileAttachment",
}

# ============================================================
# Compiled Regular Expressions
# ============================================================

PDF_HEADER_PATTERN = re.compile(rb"%PDF-\d\.\d")
PDF_EOF_PATTERN = re.compile(rb"%%EOF")
# Readers accept a header anywhere in the first 1 KB (some generators prepend bytes).
PDF_HEADER_SEARCH_BYTES = 1024


def validate(
    context: ValidationContext,
) -> None:
    """
    Perform format-specific security validation for PDF
    documents before sandbox parsing.
    """

    # ========================================================
    # Structural Validation
    # ========================================================

    _validate_header(
        context,
    )

    _validate_eof(
        context,
    )

    reader = _open_pdf(
        context,
    )

    # Before the structural checks: a password-protected file cannot be
    # read at all, and the user should be told why.
    _validate_encryption(
        context,
        reader,
    )

    _validate_xref(
        context,
        reader,
    )

    _validate_corrupted_objects(
        context,
        reader,
    )

    _validate_object_streams(
        context,
        reader,
    )

    _validate_trailer(
        context,
        reader,
    )

    _validate_object_structure(
        context,
        reader,
    )

    _validate_page_tree(
        context,
        reader,
    )

    _validate_streams(
        context,
        reader,
    )

    # ========================================================
    # Active Content Validation
    # ========================================================

    _validate_javascript(
        context,
        reader,
    )

    _validate_actions(
        context,
        reader,
    )

    _validate_uri_actions(
        context,
        reader,
    )

    _validate_rich_media(
        context,
        reader,
    )

    _validate_annotations(
        context,
        reader,
    )

    # ========================================================
    # Embedded Content Validation
    # ========================================================

    _validate_embedded_content(
        context,
        reader,
    )
    # ========================================================
    # Security Policy Validation
    # ========================================================

    _validate_security_policy(
        context,
        reader,
    )
    # ========================================================
    # Parser Safety Validation
    # ========================================================

    _validate_parser_safety(
    context,
    reader,
)


    context.security_validated = True



    # ========================================================
    # Structural Validation
    # ========================================================
def _validate_header(
    context: ValidationContext,
) -> None:
    """
    Validate the PDF file header.

    Expected:
        %PDF-x.y
    """

    try:
        with context.file_path.open("rb") as file:
            header = file.read(PDF_HEADER_SEARCH_BYTES)

    except OSError as exc:
        raise FormatSecurityError(
            "Unable to read PDF header.",
            phase="structural_validation",
            check="pdf_header",
            code="PDF_HEADER_READ_FAILED",
        ) from exc

    if not PDF_HEADER_PATTERN.search(header):
        raise FormatSecurityError(
            "Invalid PDF header.",
            phase="structural_validation",
            check="pdf_header",
            code="INVALID_PDF_HEADER",
        )

def _validate_eof(
    context: ValidationContext,
) -> None:
    """
    Validate that the PDF contains a valid EOF marker.
    """

    try:
        with context.file_path.open("rb") as file:

            file.seek(0, 2)

            file_size = file.tell()

            read_size = min(
                file_size,
                2048,
            )

            file.seek(
                -read_size,
                2,
            )

            tail = file.read()

    except OSError as exc:
        raise FormatSecurityError(
            "Unable to read PDF EOF marker.",
            phase="structural_validation",
            check="pdf_eof",
            code="PDF_EOF_READ_FAILED",
        ) from exc

    if not PDF_EOF_PATTERN.search(tail):
        raise FormatSecurityError(
            "Missing PDF EOF marker.",
            phase="structural_validation",
            check="pdf_eof",
            code="MISSING_PDF_EOF",
        )

def _decrypt_if_possible(reader: PdfReader) -> PdfReader:
    """Open permission-only encryption (empty user password) so the
    structural checks can read the pages. _validate_encryption decides."""
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass
    return reader


def _open_pdf(
    context: ValidationContext,
) -> PdfReader:
    """
    Open the PDF, strictly first.

    Many real-world PDFs have small structural errors that every reader
    repairs. Those are accepted when the lenient reader can open them; the
    active-content checks that follow still run on the repaired document.
    """

    try:
        return _decrypt_if_possible(PdfReader(
            str(
                context.file_path,
            ),
            strict=True,
        ))

    except Exception as strict_exc:
        try:
            reader = _decrypt_if_possible(PdfReader(str(context.file_path), strict=False))
            len(reader.pages)
        except Exception as exc:
            raise FormatSecurityError(
                "Malformed PDF structure.",
                phase="structural_validation",
                check="pdf_structure",
                code="INVALID_PDF_STRUCTURE",
            ) from exc

        context.warnings.append({
            "code": "PDF_REPAIRED",
            "message": f"PDF has structural errors and was opened in lenient mode: {strict_exc}",
        })
        return reader

def _validate_xref(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate that a cross-reference table exists.
    """

    if not hasattr(
        reader,
        "xref",
    ):
        raise FormatSecurityError(
            "Cross-reference table missing.",
            phase="structural_validation",
            check="xref",
            code="MISSING_XREF",
        )

    if not reader.xref:
        raise FormatSecurityError(
            "Empty cross-reference table.",
            phase="structural_validation",
            check="xref",
            code="EMPTY_XREF",
        )

def _validate_trailer(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate that the PDF trailer exists and contains
    the required root catalog.
    """

    trailer = getattr(
        reader,
        "trailer",
        None,
    )

    if not trailer:
        raise FormatSecurityError(
            "Missing PDF trailer.",
            phase="structural_validation",
            check="trailer",
            code="MISSING_TRAILER",
        )

    if "/Root" not in trailer:
        raise FormatSecurityError(
            "PDF trailer missing root catalog.",
            phase="structural_validation",
            check="trailer",
            code="MISSING_ROOT_CATALOG",
        )


def _validate_object_structure(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate indirect object structure.
    """

    try:

        object_count = len(
            reader.resolved_objects,
        )

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to resolve PDF objects.",
            phase="structural_validation",
            check="object_structure",
            code="OBJECT_RESOLUTION_FAILED",
        ) from exc

    if object_count == 0:
        raise FormatSecurityError(
            "PDF contains no indirect objects.",
            phase="structural_validation",
            check="object_structure",
            code="EMPTY_OBJECT_TREE",
        )

    if object_count > MAX_PDF_OBJECTS:
        raise FormatSecurityError(
            "PDF object count exceeds safety limit.",
            phase="structural_validation",
            check="object_structure",
            code="EXCESSIVE_OBJECT_COUNT",
        )


def _validate_corrupted_objects(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Force every page object to be resolved.

    Any corrupted indirect object should fail here.
    """

    try:

        for page in reader.pages:

            page.get_object()

    except Exception as exc:

        raise FormatSecurityError(
            "Corrupted PDF object detected.",
            phase="structural_validation",
            check="corrupted_objects",
            code="CORRUPTED_OBJECT",
        ) from exc

def _validate_object_streams(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate compressed object streams.
    """

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            if isinstance(
                contents,
                list,
            ):
                for stream in contents:
                    stream.get_data()

            else:
                contents.get_data()

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid PDF object stream.",
            phase="structural_validation",
            check="object_stream",
            code="INVALID_OBJECT_STREAM",
        ) from exc

def _validate_streams(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate every page content stream.
    """

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            if isinstance(
                contents,
                list,
            ):
                for stream in contents:

                    data = stream.get_data()

                    if len(data) > MAX_DECOMPRESSED_STREAM:
                        raise FormatSecurityError(
                            "PDF stream exceeds safety limit.",
                            phase="structural_validation",
                            check="stream_validation",
                            code="EXCESSIVE_STREAM_SIZE",
                        )

            else:

                data = contents.get_data()

                if len(data) > MAX_DECOMPRESSED_STREAM:
                    raise FormatSecurityError(
                        "PDF stream exceeds safety limit.",
                        phase="structural_validation",
                        check="stream_validation",
                        code="EXCESSIVE_STREAM_SIZE",
                    )

    except FormatSecurityError:
        raise

    except Exception as exc:

        raise FormatSecurityError(
            "Malformed PDF stream detected.",
            phase="structural_validation",
            check="stream_validation",
            code="INVALID_STREAM",
        ) from exc

def _validate_page_tree(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate page tree integrity.
    """

    try:

        page_count = len(
            reader.pages,
        )

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid page tree.",
            phase="structural_validation",
            check="page_tree",
            code="INVALID_PAGE_TREE",
        ) from exc

    if page_count == 0:
        raise FormatSecurityError(
            "PDF contains no pages.",
            phase="structural_validation",
            check="page_tree",
            code="EMPTY_PAGE_TREE",
        )

    if page_count > MAX_PDF_PAGES:
        raise FormatSecurityError(
            "PDF page count exceeds safety limit.",
            phase="structural_validation",
            check="page_tree",
            code="EXCESSIVE_PAGE_COUNT",
        )


    # ========================================================
    # Active Content Validation
    # ========================================================

def _validate_javascript(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject PDFs containing embedded JavaScript.
    """

    try:

        root = reader.trailer.get("/Root")

        if root is None:
            return

        names = root.get("/Names")

        if names and "/JavaScript" in str(names):

            raise FormatSecurityError(
                "Embedded JavaScript detected.",
                phase="active_content_validation",
                check="javascript",
                code="PDF_JAVASCRIPT_DETECTED",
            )

        open_action = root.get("/OpenAction")

        if open_action:

            action = str(open_action)

            if "/JS" in action or "/JavaScript" in action:

                raise FormatSecurityError(
                    "JavaScript action detected.",
                    phase="active_content_validation",
                    check="javascript",
                    code="PDF_JAVASCRIPT_ACTION",
                )

    except FormatSecurityError:
        raise

    except Exception:
        return

def _validate_actions(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate all executable PDF actions.
    """

    _validate_launch_actions(
        context,
        reader,
    )

    _validate_open_actions(
        context,
        reader,
    )

    _validate_uri_actions(
        context,
        reader,
    )

def _validate_launch_actions(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject Launch actions.
    """

    try:

        root = reader.trailer["/Root"]

        if "/Launch" in str(root):

            raise FormatSecurityError(
                "Launch action detected.",
                phase="active_content_validation",
                check="launch_action",
                code="PDF_LAUNCH_ACTION",
            )

    except KeyError:
        return

def _validate_open_actions(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject automatic OpenAction execution.
    """

    try:

        root = reader.trailer["/Root"]

        if "/OpenAction" in root:

            raise FormatSecurityError(
                "OpenAction detected.",
                phase="active_content_validation",
                check="open_action",
                code="PDF_OPEN_ACTION",
            )

    except KeyError:
        return

def _validate_uri_actions(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject dangerous URI actions.
    """

    try:

        for page in reader.pages:

            annotations = page.get("/Annots")

            if not annotations:
                continue

            for annotation in annotations:

                obj = annotation.get_object()

                action = obj.get("/A")

                if not action:
                    continue

                uri = action.get("/URI")

                if not uri:
                    continue

                uri = str(uri).lower()

                if uri.startswith(DANGEROUS_URI_SCHEMES):

                    raise FormatSecurityError(
                        "Dangerous URI detected.",
                        phase="active_content_validation",
                        check="uri_action",
                        code="PDF_DANGEROUS_URI",
                    )

    except FormatSecurityError:
        raise

    except Exception:
        return

def _validate_rich_media(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate interactive multimedia content.
    """

    _validate_flash_content(
        context,
        reader,
    )

    _validate_embedded_media(
        context,
        reader,
    )

def _validate_flash_content(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject Flash content.
    """

    try:

        root = reader.trailer["/Root"]

        if "/Flash" in str(root):

            raise FormatSecurityError(
                "Flash content detected.",
                phase="active_content_validation",
                check="flash_content",
                code="PDF_FLASH_CONTENT",
            )

    except KeyError:
        return

def _validate_embedded_media(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject embedded multimedia objects.
    """

    MEDIA_TYPES = {
        "/RichMedia",
        "/Movie",
        "/Sound",
        "/3D",
    }

    try:

        trailer = str(
            reader.trailer,
        )

        for media in MEDIA_TYPES:

            if media in trailer:

                raise FormatSecurityError(
                    f"{media} detected.",
                    phase="active_content_validation",
                    check="embedded_media",
                    code="PDF_EMBEDDED_MEDIA",
                )

    except FormatSecurityError:
        raise

def _validate_annotations(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate PDF annotations.
    """

    try:

        for page in reader.pages:

            annotations = page.get(
                "/Annots",
            )

            if not annotations:
                continue

            for annotation in annotations:

                obj = annotation.get_object()

                _validate_annotation_subtype(
                    context,
                    obj,
                )

                _validate_annotation_action(
                    context,
                    obj,
                )

    except FormatSecurityError:
        raise

    except Exception:
        return

def _validate_annotation_subtype(
    context: ValidationContext,
    annotation,
) -> None:
    """
    Reject dangerous annotation subtypes.
    """

    subtype = annotation.get(
        "/Subtype",
    )

    if subtype in {
        "/RichMedia",
        "/Movie",
        "/Screen",
        "/Sound",
        "/FileAttachment",
    }:

        raise FormatSecurityError(
            f"Dangerous annotation subtype: {subtype}",
            phase="active_content_validation",
            check="annotation_subtype",
            code="PDF_DANGEROUS_ANNOTATION",
        )

def _validate_annotation_action(
    context: ValidationContext,
    annotation,
) -> None:
    """
    Reject annotations containing executable actions.
    """

    action = annotation.get(
        "/A",
    )

    if not action:
        return

    action = str(
        action,
    )

    DANGEROUS_ACTIONS = (
        "/Launch",
        "/JavaScript",
        "/JS",
        "/SubmitForm",
        "/ImportData",
    )

    for dangerous in DANGEROUS_ACTIONS:

        if dangerous in action:

            raise FormatSecurityError(
                "Executable annotation action detected.",
                phase="active_content_validation",
                check="annotation_action",
                code="PDF_EXECUTABLE_ANNOTATION",
            )

    # ========================================================
    # Embedded Content Validation
    # ========================================================

def _validate_embedded_content(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate embedded content contained within the PDF.
    """

    _validate_embedded_files(
        context,
        reader,
    )

    _validate_embedded_executables(
        context,
        reader,
    )

    _validate_file_attachments(
        context,
        reader,
    )

def _embedded_file_specs(names_tree) -> list:
    """
    File specifications in an /EmbeddedFiles name tree (a flat /Names array
    of name/filespec pairs, or /Kids nodes holding more of them).
    """

    specs = []
    pending = [names_tree]
    seen = 0

    while pending:
        node = pending.pop().get_object()

        # A hostile tree could be huge or cyclic; nobody embeds this many files.
        seen += 1
        if seen > 1000:
            raise ValueError("Embedded file tree too large")

        pairs = node.get("/Names") or []
        specs.extend(pairs[i].get_object() for i in range(1, len(pairs), 2))
        pending.extend(node.get("/Kids") or [])

    return specs


def _is_c2pa_manifest(spec) -> bool:
    """
    A C2PA "Content Credentials" manifest: provenance metadata that ChatGPT,
    Adobe and other tools attach to the PDFs they generate. It is a JUMBF
    container of signed metadata, never extracted or run here.
    """

    try:
        if spec.get("/AFRelationship") != "/C2PA_Manifest":
            return False

        stream = spec["/EF"]["/F"].get_object()

        if stream.get("/Subtype") != "/application/c2pa":
            return False

        # JUMBF superbox: 4-byte length, then the "jumb" box type.
        return stream.get_data()[4:8] == b"jumb"

    except Exception:
        return False


def _validate_embedded_files(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject PDFs containing embedded files, except C2PA Content Credentials
    manifests (see _is_c2pa_manifest).
    """

    rejection = FormatSecurityError(
        "Embedded files detected.",
        phase="embedded_content_validation",
        check="embedded_files",
        code="PDF_EMBEDDED_FILES",
    )

    try:

        root = reader.trailer.get("/Root")

        if root is None:
            return

        names = root.get_object().get("/Names")

        if names is None:
            return

        embedded = names.get_object().get("/EmbeddedFiles")

        if embedded is None:
            return

        specs = _embedded_file_specs(embedded)

    except Exception:
        # An /EmbeddedFiles tree that can't be read can't be cleared either.
        raise rejection

    if not all(_is_c2pa_manifest(spec) for spec in specs):
        raise rejection

def _validate_embedded_executables(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject embedded executable payloads.
    """

    EXECUTABLE_EXTENSIONS = {
        ".exe",
        ".dll",
        ".msi",
        ".bat",
        ".cmd",
        ".com",
        ".scr",
        ".ps1",
        ".jar",
        ".vbs",
    }

    try:

        trailer = str(
            reader.trailer,
        ).lower()

        for extension in EXECUTABLE_EXTENSIONS:

            if extension in trailer:

                raise FormatSecurityError(
                    "Embedded executable detected.",
                    phase="embedded_content_validation",
                    check="embedded_executable",
                    code="PDF_EMBEDDED_EXECUTABLE",
                )

    except FormatSecurityError:
        raise

    except Exception:
        return

def _validate_file_attachments(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject file attachment annotations.
    """

    try:

        for page in reader.pages:

            annotations = page.get(
                "/Annots",
            )

            if not annotations:
                continue

            for annotation in annotations:

                obj = annotation.get_object()

                subtype = obj.get(
                    "/Subtype",
                )

                if subtype == "/FileAttachment":

                    raise FormatSecurityError(
                        "File attachment detected.",
                        phase="embedded_content_validation",
                        check="file_attachment",
                        code="PDF_FILE_ATTACHMENT",
                    )

    except FormatSecurityError:
        raise

    except Exception:
        return

    # ========================================================
    # Security Policy Validation
    # ========================================================

def _validate_security_policy(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate ContextAPI PDF security policy.
    """

    _validate_incremental_updates(
        context,
    )

def _validate_encryption(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Reject password-protected PDF documents.

    PDFs that are encrypted only to restrict printing/copying open with an
    empty user password; those are accepted (the parser decrypts them).
    """

    if reader.is_encrypted:

        try:
            opened = bool(reader.decrypt(""))
        except Exception:
            opened = False

        if opened:
            context.warnings.append({
                "code": "PDF_ENCRYPTED_NO_PASSWORD",
                "message": "PDF is encrypted with an empty password (permissions only).",
            })
            return

        raise FormatSecurityError(
            "Password-protected PDF documents are not supported. Remove the password and upload again.",
            phase="security_policy_validation",
            check="encryption",
            code="PDF_ENCRYPTED",
        )

def _validate_incremental_updates(
    context: ValidationContext,
) -> None:
    """
    Note PDFs containing incremental updates.

    Any PDF saved more than once (edited, signed, exported by Word) has
    them. Only the final revision is parsed and indexed, so earlier
    revisions never reach the knowledge base: record a warning, not a
    rejection.
    """

    try:

        data = context.file_path.read_bytes()

    except OSError as exc:

        raise FormatSecurityError(
            "Unable to inspect PDF incremental updates.",
            phase="security_policy_validation",
            check="incremental_updates",
            code="PDF_INCREMENTAL_UPDATE_READ_FAILED",
        ) from exc

    eof_count = data.count(
        b"%%EOF",
    )

    if eof_count > 1:

        context.warnings.append({
            "code": "PDF_INCREMENTAL_UPDATES",
            "message": f"PDF has {eof_count - 1} incremental update(s); only the final revision is used.",
        })

    # ========================================================
    # Parser Safety Validation
    # ========================================================

def _validate_parser_safety(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate parser safety constraints.
    """

    _validate_object_limits(
        context,
        reader,
    )

    _validate_object_references(
        context,
        reader,
    )

    _validate_stream_limits(
        context,
        reader,
    )

    _validate_compression(
        context,
        reader,
    )


def _validate_object_limits(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate PDF object limits.
    """

    _validate_object_count(
        context,
        reader,
    )

    _validate_page_count(
        context,
        reader,
    )

def _validate_object_count(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate maximum object count.
    """

    object_count = len(
        reader.resolved_objects,
    )

    if object_count > MAX_PDF_OBJECTS:

        raise FormatSecurityError(
            "PDF object limit exceeded.",
            phase="parser_safety_validation",
            check="object_count",
            code="PDF_OBJECT_LIMIT_EXCEEDED",
        )

def _validate_page_count(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate maximum page count.
    """

    page_count = len(
        reader.pages,
    )

    if page_count > MAX_PDF_PAGES:

        raise FormatSecurityError(
            "PDF page limit exceeded.",
            phase="parser_safety_validation",
            check="page_count",
            code="PDF_PAGE_LIMIT_EXCEEDED",
        )

def _validate_object_references(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate indirect object references.
    """

    _validate_recursive_objects(
        context,
        reader,
    )

    _validate_infinite_references(
        context,
        reader,
    )

def _validate_recursive_objects(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Detect excessive recursive object depth.
    """

    visited = set()

    def walk(
        obj,
        depth: int = 0,
    ):

        if depth > MAX_OBJECT_REFERENCE_DEPTH:

            raise FormatSecurityError(
                "Recursive object depth exceeded.",
                phase="parser_safety_validation",
                check="recursive_objects",
                code="PDF_RECURSIVE_OBJECTS",
            )

        obj_id = id(obj)

        if obj_id in visited:
            return

        visited.add(obj_id)

        if isinstance(
            obj,
            dict,
        ):
            for value in obj.values():
                walk(
                    value,
                    depth + 1,
                )

        elif isinstance(
            obj,
            list,
        ):
            for value in obj:
                walk(
                    value,
                    depth + 1,
                )

    walk(
        reader.trailer,
    )


def _validate_infinite_references(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Detect circular object references.
    """

    visited = set()

    stack = set()

    def walk(obj):

        obj_id = id(obj)

        if obj_id in stack:

            raise FormatSecurityError(
                "Circular object reference detected.",
                phase="parser_safety_validation",
                check="infinite_references",
                code="PDF_CIRCULAR_REFERENCE",
            )

        if obj_id in visited:
            return

        visited.add(
            obj_id,
        )

        stack.add(
            obj_id,
        )

        if isinstance(
            obj,
            dict,
        ):
            for value in obj.values():
                walk(value)

        elif isinstance(
            obj,
            list,
        ):
            for value in obj:
                walk(value)

        stack.remove(
            obj_id,
        )

    walk(
        reader.trailer,
    )


def _validate_stream_limits(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate PDF stream safety limits.
    """

    _validate_stream_count(
        context,
        reader,
    )

    _validate_stream_size(
        context,
        reader,
    )

    _validate_decompressed_stream_size(
        context,
        reader,
    )

def _validate_stream_count(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate the number of PDF streams.
    """

    stream_count = 0

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            if isinstance(
                contents,
                list,
            ):
                stream_count += len(contents)

            else:
                stream_count += 1

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to inspect PDF streams.",
            phase="parser_safety_validation",
            check="stream_count",
            code="PDF_STREAM_COUNT_FAILED",
        ) from exc

    if stream_count > MAX_PDF_STREAMS:

        raise FormatSecurityError(
            "PDF stream count exceeds limit.",
            phase="parser_safety_validation",
            check="stream_count",
            code="PDF_STREAM_LIMIT_EXCEEDED",
        )

def _validate_stream_size(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate compressed stream sizes.
    """

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            streams = (
                contents
                if isinstance(contents, list)
                else [contents]
            )

            for stream in streams:

                raw = getattr(
                    stream,
                    "_data",
                    b"",
                )

                if len(raw) > MAX_STREAM_SIZE:

                    raise FormatSecurityError(
                        "PDF stream exceeds compressed size limit.",
                        phase="parser_safety_validation",
                        check="stream_size",
                        code="PDF_STREAM_SIZE_EXCEEDED",
                    )

    except FormatSecurityError:
        raise

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to validate stream sizes.",
            phase="parser_safety_validation",
            check="stream_size",
            code="PDF_STREAM_SIZE_FAILED",
        ) from exc

def _validate_decompressed_stream_size(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate decompressed stream sizes.
    """

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            streams = (
                contents
                if isinstance(contents, list)
                else [contents]
            )

            for stream in streams:

                data = stream.get_data()

                if len(data) > MAX_DECOMPRESSED_STREAM:

                    raise FormatSecurityError(
                        "PDF decompressed stream exceeds limit.",
                        phase="parser_safety_validation",
                        check="decompressed_stream",
                        code="PDF_DECOMPRESSED_STREAM_EXCEEDED",
                    )

    except FormatSecurityError:
        raise

    except Exception as exc:

        raise FormatSecurityError(
            "Unable to inspect decompressed streams.",
            phase="parser_safety_validation",
            check="decompressed_stream",
            code="PDF_DECOMPRESSED_STREAM_FAILED",
        ) from exc

def _validate_compression(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Validate PDF compression safety.
    """

    _validate_compression_ratio(
        context,
        reader,
    )

    _validate_compression_bomb(
        context,
        reader,
    )

def _validate_compression_ratio(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Detect excessive compression ratios.
    """

    MAX_RATIO = 100

    try:

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            streams = (
                contents
                if isinstance(contents, list)
                else [contents]
            )

            for stream in streams:

                compressed = len(
                    getattr(
                        stream,
                        "_data",
                        b"",
                    )
                )

                decompressed = len(
                    stream.get_data()
                )

                if compressed == 0:
                    continue

                ratio = decompressed / compressed

                if ratio > MAX_RATIO:

                    raise FormatSecurityError(
                        "Excessive compression ratio detected.",
                        phase="parser_safety_validation",
                        check="compression_ratio",
                        code="PDF_COMPRESSION_RATIO_EXCEEDED",
                    )

    except FormatSecurityError:
        raise

    except Exception:
        return

def _validate_compression_bomb(
    context: ValidationContext,
    reader: PdfReader,
) -> None:
    """
    Detect potential PDF compression bombs.
    """

    try:

        total_decompressed = 0

        for page in reader.pages:

            contents = page.get_contents()

            if contents is None:
                continue

            streams = (
                contents
                if isinstance(contents, list)
                else [contents]
            )

            for stream in streams:

                total_decompressed += len(
                    stream.get_data()
                )

                if total_decompressed > MAX_DECOMPRESSED_STREAM:

                    raise FormatSecurityError(
                        "Potential compression bomb detected.",
                        phase="parser_safety_validation",
                        check="compression_bomb",
                        code="PDF_COMPRESSION_BOMB",
                    )

    except FormatSecurityError:
        raise

    except Exception:
        return

    # ========================================================
    # Consistency Validation
    # ========================================================
