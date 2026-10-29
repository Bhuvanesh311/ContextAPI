"""
Parsers for PowerPoint, Excel, HTML, images and legacy/OpenDocument
office files.

All of them turn the file into plain text (tables as tab-separated rows) and
return a NormalizedDocument; chunking treats them like any other document.
They run inside the parser sandbox.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import FileParsingError, SourceFileNotFoundError
from app.knowledge.parsing.ocr import ocr_image, scratch_dir
from app.knowledge.parsing.schemas import NormalizedDocument, ParsingRequest

logger = logging.getLogger(__name__)

MAX_SOURCE_BYTES = 200 * 1024 * 1024
MAX_SHEET_CELLS = 2_000_000
LIBREOFFICE_TIMEOUT_SECONDS = 180

_BLANK_LINES = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t ]+")


def _clean(text: str) -> str:
    lines = [_SPACES.sub(" ", line).strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()


def _check_source(file_path: Path) -> None:
    if not file_path.is_file():
        raise SourceFileNotFoundError(f"Source file not found: {file_path.name}")
    if file_path.stat().st_size > MAX_SOURCE_BYTES:
        raise FileParsingError(f"File exceeds parser limit of {MAX_SOURCE_BYTES} bytes: {file_path.name}")


def _document(
    request: ParsingRequest,
    file_path: Path,
    source_format: ParserFormat,
    content: str,
    metadata: dict,
    page_count: int | None = None,
) -> NormalizedDocument:
    content = _clean(content)
    return NormalizedDocument(
        document_id=request.document_id,
        file_name=file_path.name,
        source_format=source_format,
        content=content,
        metadata={
            "parser": metadata.pop("parser"),
            "format": source_format.value,
            "file_extension": file_path.suffix.lower(),
            "file_size_bytes": file_path.stat().st_size,
            **metadata,
        },
        page_count=page_count,
        character_count=len(content),
        word_count=len(content.split()),
        mime_type=request.mime_type,
    )


# ---------------------------------------------------------------- PowerPoint

class PPTXParser(BaseParser):
    parser_name = "pptx_parser"
    supported_extensions = (".pptx",)

    def parse(self, file_path: Path, request: ParsingRequest) -> NormalizedDocument:
        _check_source(file_path)
        try:
            from pptx import Presentation
        except ImportError as exc:  # pragma: no cover - sandbox image ships it
            raise FileParsingError("python-pptx is not installed") from exc

        try:
            presentation = Presentation(str(file_path))
        except Exception as exc:
            raise FileParsingError(f"Unable to open presentation: {file_path.name}") from exc

        slides_text: list[str] = []
        table_count = 0
        for number, slide in enumerate(presentation.slides, start=1):
            parts = [f"Slide {number}"]
            for shape in slide.shapes:
                if getattr(shape, "has_table", False) and shape.has_table:
                    table_count += 1
                    for row in shape.table.rows:
                        parts.append("\t".join(cell.text.strip() for cell in row.cells))
                elif getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                    text = shape.text_frame.text.strip()
                    if text:
                        parts.append(text)
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    parts.append(f"Notes: {notes}")
            slides_text.append("\n".join(parts))

        return _document(
            request, file_path, ParserFormat.PPTX, "\n\n".join(slides_text),
            {"parser": self.parser_name, "slide_count": len(slides_text), "table_count": table_count},
            page_count=len(slides_text),
        )


# --------------------------------------------------------------------- Excel

class XLSXParser(BaseParser):
    parser_name = "xlsx_parser"
    supported_extensions = (".xlsx",)

    def parse(self, file_path: Path, request: ParsingRequest) -> NormalizedDocument:
        _check_source(file_path)
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover
            raise FileParsingError("openpyxl is not installed") from exc

        try:
            workbook = load_workbook(str(file_path), read_only=True, data_only=True)
        except Exception as exc:
            raise FileParsingError(f"Unable to open workbook: {file_path.name}") from exc

        sheets_text: list[str] = []
        cells = 0
        truncated = False
        try:
            for sheet in workbook.worksheets:
                rows: list[str] = [f"Sheet: {sheet.title}"]
                for row in sheet.iter_rows(values_only=True):
                    values = ["" if value is None else str(value).strip() for value in row]
                    while values and not values[-1]:
                        values.pop()
                    if not values:
                        continue
                    cells += len(values)
                    if cells > MAX_SHEET_CELLS:
                        truncated = True
                        break
                    rows.append("\t".join(values))
                sheets_text.append("\n".join(rows))
                if truncated:
                    break
        finally:
            workbook.close()

        warnings = []
        if truncated:
            warnings.append({"code": "XLSX_TRUNCATED", "message": f"Only the first {MAX_SHEET_CELLS} cells were read."})

        return _document(
            request, file_path, ParserFormat.XLSX, "\n\n".join(sheets_text),
            {"parser": self.parser_name, "sheet_count": len(sheets_text), "warnings": warnings},
        )


# ---------------------------------------------------------------------- HTML

class HTMLParser(BaseParser):
    parser_name = "html_parser"
    supported_extensions = (".html", ".htm")

    def parse(self, file_path: Path, request: ParsingRequest) -> NormalizedDocument:
        _check_source(file_path)
        from bs4 import BeautifulSoup

        try:
            soup = BeautifulSoup(file_path.read_bytes(), "lxml")
        except Exception as exc:
            raise FileParsingError(f"Unable to parse HTML: {file_path.name}") from exc

        # Scripts and styles are never run; they are just not content.
        for tag in soup(["script", "style", "noscript", "template", "svg"]):
            tag.decompose()

        title = soup.title.get_text(strip=True) if soup.title else ""
        for cell in soup.find_all(["td", "th"]):
            cell.append("\t")
        text = soup.get_text("\n")
        if title and not text.lstrip().startswith(title):
            text = f"{title}\n\n{text}"

        return _document(
            request, file_path, ParserFormat.HTML, text,
            {"parser": self.parser_name, "title": title or None},
        )


# -------------------------------------------------------------------- Images

class ImageParser(BaseParser):
    parser_name = "image_ocr_parser"
    supported_extensions = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")

    def parse(self, file_path: Path, request: ParsingRequest) -> NormalizedDocument:
        _check_source(file_path)
        text = ocr_image(file_path)
        if not text.strip():
            raise FileParsingError(f"No readable text found in image: {file_path.name}")
        return _document(
            request, file_path, ParserFormat.IMAGE, text,
            {"parser": self.parser_name, "extraction_strategies": ["ocr"]},
            page_count=1,
        )


# ------------------------------------------------- Legacy / OpenDocument

class LegacyOfficeParser(BaseParser):
    """
    .doc .rtf .odt -> .docx, .xls .ods -> .xlsx, .ppt .odp -> .pptx with
    LibreOffice (headless, no network), then the matching parser.
    """

    parser_name = "legacy_office_parser"
    supported_extensions = (".doc", ".rtf", ".odt", ".xls", ".ods", ".ppt", ".odp")

    TARGETS = {
        ".doc": ".docx", ".rtf": ".docx", ".odt": ".docx",
        ".xls": ".xlsx", ".ods": ".xlsx",
        ".ppt": ".pptx", ".odp": ".pptx",
    }

    def parse(self, file_path: Path, request: ParsingRequest) -> NormalizedDocument:
        _check_source(file_path)
        extension = file_path.suffix.lower()
        target = self.TARGETS.get(extension)
        if target is None:
            raise FileParsingError(f"Unsupported legacy office extension: {extension}")

        with tempfile.TemporaryDirectory(dir=scratch_dir()) as tmp:
            tmp_dir = Path(tmp)
            converted = self._convert(file_path, target, tmp_dir)

            from app.knowledge.parsing.parsers.document.docx import DOCXParser

            delegate = {".docx": DOCXParser(), ".xlsx": XLSXParser(), ".pptx": PPTXParser()}[target]
            converted_request = request.model_copy(update={
                "extension": target,
                "original_filename": converted.name,
                "detected_format": {
                    ".docx": ParserFormat.DOCX,
                    ".xlsx": ParserFormat.XLSX,
                    ".pptx": ParserFormat.PPTX,
                }[target],
            })
            parsed = delegate.parse(converted, converted_request)

        metadata = dict(parsed.metadata)
        metadata.update({
            "converted_from": extension,
            "converted_to": target,
            "parser": f"{self.parser_name}+{metadata.get('parser', delegate.parser_name)}",
            "format": ParserFormat.LEGACY_OFFICE.value,
            "file_extension": extension,
            "file_size_bytes": file_path.stat().st_size,
        })
        return NormalizedDocument(
            document_id=request.document_id,
            file_name=file_path.name,
            source_format=ParserFormat.LEGACY_OFFICE,
            content=parsed.content,
            metadata=metadata,
            page_count=parsed.page_count,
            character_count=parsed.character_count,
            word_count=parsed.word_count,
            mime_type=request.mime_type,
        )

    @staticmethod
    def _convert(file_path: Path, target: str, out_dir: Path) -> Path:
        profile = out_dir / "lo-profile"
        command = [
            "soffice", "--headless", "--norestore", "--nologo", "--nolockcheck",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", target.lstrip("."),
            "--outdir", str(out_dir),
            str(file_path),
        ]
        env = {**os.environ, "HOME": str(out_dir), "TMPDIR": str(out_dir)}
        try:
            completed = subprocess.run(
                command, capture_output=True, timeout=LIBREOFFICE_TIMEOUT_SECONDS, env=env, check=False,
            )
        except FileNotFoundError as exc:
            raise FileParsingError("LibreOffice is not installed in the parser sandbox") from exc
        except subprocess.TimeoutExpired as exc:
            raise FileParsingError(f"Converting {file_path.name} took too long") from exc

        converted = out_dir / f"{file_path.stem}{target}"
        if completed.returncode != 0 or not converted.is_file():
            detail = completed.stderr.decode("utf-8", "replace")[-300:]
            raise FileParsingError(f"Could not convert {file_path.name}: {detail}")
        return converted
