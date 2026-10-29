"""Stage 3 PDF check: embedded files are rejected, except C2PA manifests."""

import hashlib
import io
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import NameObject

from app.knowledge.security.stage_3.context import ValidationContext
from app.knowledge.security.stage_3.exceptions import FormatSecurityError
from app.knowledge.security.stage_3.phase_b.validators import pdf

# A JUMBF superbox header, as C2PA manifests start.
C2PA_DATA = b"\x00\x00\x00\x40jumb\x00\x00\x00\x1ejumdc2pa" + b"\x00" * 40


def _pdf(tmp_path: Path, attachment=None, c2pa=False) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    if attachment:
        name, data = attachment
        writer.add_attachment(name, data)
        if c2pa:
            spec = writer.root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
            spec[NameObject("/AFRelationship")] = NameObject("/C2PA_Manifest")
            spec["/EF"]["/F"].get_object()[NameObject("/Subtype")] = NameObject("/application/c2pa")
    buffer = io.BytesIO()
    writer.write(buffer)
    path = tmp_path / "doc.pdf"
    path.write_bytes(buffer.getvalue())
    return path


def _validate(path: Path) -> None:
    data = path.read_bytes()
    pdf._validate_embedded_files(
        ValidationContext(
            document_id="DOC1",
            project_id="P1",
            upload_id="UPL1",
            parent_document_id=None,
            original_filename=path.name,
            file_path=path,
            extension="pdf",
            mime_type="application/pdf",
            file_size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        ),
        pdf.PdfReader(path),
    )


def test_pdf_without_attachments_passes(tmp_path):
    _validate(_pdf(tmp_path))


def test_c2pa_content_credentials_pass(tmp_path):
    # What ChatGPT and other generators attach to the PDFs they create.
    _validate(_pdf(tmp_path, ("Content Credentials", C2PA_DATA), c2pa=True))


def test_ordinary_attachment_is_rejected(tmp_path):
    with pytest.raises(FormatSecurityError) as error:
        _validate(_pdf(tmp_path, ("payload.exe", b"MZ" + b"\x00" * 64)))
    assert error.value.code == "PDF_EMBEDDED_FILES"


def test_attachment_only_labelled_c2pa_is_rejected(tmp_path):
    # Right labels, but the content is not a JUMBF manifest.
    with pytest.raises(FormatSecurityError):
        _validate(_pdf(tmp_path, ("Content Credentials", b"MZ" + b"\x00" * 64), c2pa=True))
