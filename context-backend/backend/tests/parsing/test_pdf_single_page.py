import io
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.knowledge.parsing.enums import ParserFormat, ParserStatus
from app.knowledge.parsing.exceptions import OutputValidationError
from app.knowledge.parsing.parsers.document.pdf import PDFParser
from app.knowledge.parsing.schemas import ParsingRequest

SCAN_TEXT = "Python is a high-level, general-purpose programming language. " * 4


def _image_page_pdf(path: Path, caption: str | None) -> Path:
    """One page that is a picture (a scan), optionally with a tiny text layer."""
    buffer = io.BytesIO()
    Image.new("RGB", (400, 560), "white").save(buffer, "PDF")
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(buffer.getvalue())))
    if caption:
        page = writer.pages[0]
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        resources = page["/Resources"]
        resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 10 Tf 20 20 Td ({caption}) Tj ET".encode())
        contents = page.get_contents()
        contents.set_data(contents.get_data() + b"\n" + stream.get_data())
        page.replace_contents(contents)
    writer.write(path)
    return path


def _blank_pdf(path: Path) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(path)
    return path


def _request(path: Path) -> ParsingRequest:
    return ParsingRequest(
        document_id="DOC1", project_id="P1", upload_id="U1", original_filename=path.name,
        extension=".pdf", mime_type="application/pdf", detected_format=ParserFormat.PDF,
        size_bytes=path.stat().st_size, checksum="x", quarantine_bucket="q", source_object_key="k",
        parsed_bucket="p", parsed_object_key="k", status=ParserStatus.READY_FOR_PARSING,
    )


def test_scan_with_small_text_layer_is_read_with_ocr(tmp_path):
    pdf = _image_page_pdf(tmp_path / "scan.pdf", caption="Scanned with CamScanner")

    with patch("app.knowledge.parsing.parsers.document.pdf.ocr_pdf_pages", return_value={1: SCAN_TEXT}) as ocr:
        document = PDFParser().parse(pdf, _request(pdf))

    ocr.assert_called_once()
    assert ocr.call_args.args[1] == [1]
    assert "general-purpose programming language" in document.content


def test_blank_pdf_fails_with_clear_message(tmp_path):
    pdf = _blank_pdf(tmp_path / "blank.pdf")

    with patch("app.knowledge.parsing.parsers.document.pdf.ocr_pdf_pages", return_value={}):
        with pytest.raises(OutputValidationError, match="No readable text"):
            PDFParser().parse(pdf, _request(pdf))


def test_control_characters_are_cleaned_before_validation():
    # Bullet glyphs without a ToUnicode map are extracted as DEL (U+007F),
    # which post-parse validation rejects as a forbidden control character.
    text = PDFParser._normalize_text("Jan 2025\n\x7f Developed\x0c REST\x01 APIs\tfast")

    assert text == "Jan 2025\n\u2022 Developed REST APIs fast"
