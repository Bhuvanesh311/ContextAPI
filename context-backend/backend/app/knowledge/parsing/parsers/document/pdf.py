from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.ocr import ocr_pdf_pages
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    OutputValidationError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import (
    NormalizedDocument,
    ParsingRequest,
)

logger = logging.getLogger(__name__)

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class PDFParser(BaseParser):

    parser_name = "pdf_parser"
    supported_extensions = (".pdf",)

    MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024
    MAX_PAGE_COUNT = 10_000
    MAX_PAGE_CONTENT_SIZE = 32 * 1024 * 1024

    # A page with an image and less text than this is treated as a scan:
    # its text layer is often only a page number, stamp or "Scanned with
    # CamScanner" watermark, and the real content is in the image.
    OCR_SHORT_TEXT_CHARS = 200

    PLAIN_SPACE_WIDTHS = (
        200,
        300,
        400,
        500,
    )

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:

        self._validate_input(
            file_path=file_path,
            request=request,
        )

        try:
            reader = PdfReader(
                file_path,
                strict=False,
            )

            if reader.is_encrypted:
                self._handle_encryption(
                    reader,
                    file_path,
                )

            page_count = len(reader.pages)

            if page_count > self.MAX_PAGE_COUNT:
                raise FileParsingError(
                    f"PDF exceeds maximum supported page count "
                    f"of {self.MAX_PAGE_COUNT}: {file_path.name}"
                )

            pages: list[dict] = []
            document_parts: list[str] = []
            strategies: list[str] = []
            warnings: list[dict[str, str]] = []

            image_pages: set[int] = set()

            for page_number, page in enumerate(
                reader.pages,
                start=1,
            ):

                if self._has_images(page):
                    image_pages.add(page_number)

                self._check_page_content_size(
                    page,
                    page_number,
                )

                raw_text, strategy = self._extract_page(page)

                text = self._normalize_text(raw_text)

                pages.append(
                    {
                        "page_number": page_number,
                        "content": text,
                        "character_count": len(text),
                        "word_count": len(text.split()),
                        "extraction_strategy": strategy,
                    }
                )

                if strategy:
                    strategies.append(strategy)

            # Pages without a text layer (scans, "Print to PDF" output), and
            # scanned pages whose text layer is only a few words: render and
            # OCR them, keeping whichever reading has more text.
            ocr_pages = [
                p["page_number"]
                for p in pages
                if not p["content"]
                or (
                    p["page_number"] in image_pages
                    and len(p["content"]) < self.OCR_SHORT_TEXT_CHARS
                )
            ]
            if ocr_pages:
                ocr_text = ocr_pdf_pages(file_path, ocr_pages)
                for page_info in pages:
                    text = self._normalize_text(ocr_text.get(page_info["page_number"], ""))
                    if len(text) > len(page_info["content"]):
                        page_info.update(
                            content=text,
                            character_count=len(text),
                            word_count=len(text.split()),
                            extraction_strategy="ocr",
                        )
                        strategies.append("ocr")
                if ocr_text:
                    warnings.append(
                        {
                            "code": "PDF_OCR_USED",
                            "severity": "INFO",
                            "message": f"{len(ocr_text)} page(s) had no text layer and were read with OCR.",
                        }
                    )

            for page_info in pages:
                if page_info["content"]:
                    document_parts.append(page_info["content"])
                else:
                    warnings.append(
                        {
                            "code": "PDF_EMPTY_PAGE",
                            "severity": "INFO",
                            "message": (
                                f"Page {page_info['page_number']} has "
                                "no extractable text."
                            ),
                        }
                    )

            content = "\n\n".join(
                document_parts
            ).strip()

            if not content:
                # Same result on every attempt: reported as a validation
                # failure so the run fails at once instead of retrying.
                raise OutputValidationError(
                    f"No readable text found in {file_path.name}: the PDF is blank, "
                    "or the scan is too unclear to read."
                )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.PDF,
                content=content,
                metadata=self._build_metadata(
                    file_path=file_path,
                    reader=reader,
                    pages=pages,
                    strategies=strategies,
                    warnings=warnings,
                ),
                page_count=page_count,
                character_count=len(content),
                word_count=len(content.split()),
                mime_type=request.mime_type,
            )

        except (FileParsingError, OutputValidationError):
            raise

        except Exception as exc:
            logger.exception(
                "PDF parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )

            raise FileParsingError(
                f"Failed to parse PDF file: {file_path.name}"
            ) from exc

    @staticmethod
    def _has_images(page: object) -> bool:
        """True when the page draws at least one image (directly or in a form)."""
        try:
            resources = page.get("/Resources") or {}
            pending = [resources.get("/XObject") or {}]
            seen = 0
            while pending and seen < 50:
                xobjects = pending.pop()
                for ref in xobjects.values():
                    seen += 1
                    obj = ref.get_object()
                    subtype = obj.get("/Subtype")
                    if subtype == "/Image":
                        return True
                    if subtype == "/Form":
                        pending.append((obj.get("/Resources") or {}).get("/XObject") or {})
        except Exception:
            return False
        return False

    # ============================================================
    # Validation
    # ============================================================

    @classmethod
    def _validate_input(
        cls,
        file_path: Path,
        request: ParsingRequest,
    ) -> None:

        if not file_path.exists():
            raise SourceFileNotFoundError(
                f"Source file not found: {file_path}"
            )

        if not file_path.is_file():
            raise SourceFileNotFoundError(
                f"Invalid source file: {file_path}"
            )

        if file_path.suffix.lower() not in cls.supported_extensions:
            raise FileParsingError(
                "PDF parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.PDF:
            raise FileParsingError(
                "PDF parser received a non-PDF detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"PDF file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"PDF file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: "
                f"{file_path.name}"
            )

    # ============================================================
    # Encryption
    # ============================================================

    @staticmethod
    def _handle_encryption(
        reader: PdfReader,
        file_path: Path,
    ) -> None:

        try:
            result = reader.decrypt("")

            if not result:
                raise FileParsingError(
                    f"Encrypted PDF cannot be opened: "
                    f"{file_path.name}"
                )

        except FileParsingError:
            raise

        except Exception as exc:
            raise FileParsingError(
                f"Unable to decrypt PDF: {file_path.name}"
            ) from exc

    # ============================================================
    # Page validation
    # ============================================================

    @classmethod
    def _check_page_content_size(
        cls,
        page: object,
        page_number: int,
    ) -> None:

        try:
            text = page.extract_text(  # type: ignore[attr-defined]
                extraction_mode="layout",
                layout_mode_space_vertically=False,
                layout_mode_strip_rotated=False,
            ) or ""

            if len(text.encode("utf-8")) > cls.MAX_PAGE_CONTENT_SIZE:
                raise FileParsingError(
                    f"PDF page {page_number} exceeds maximum "
                    f"supported extracted content size."
                )

        except FileParsingError:
            raise

        except Exception:
            # Extraction itself is handled later by _extract_page().
            pass

    # ============================================================
    # Page extraction
    # ============================================================

    def _extract_page(
        self,
        page: object,
    ) -> tuple[str, str]:

        candidates: list[tuple[str, str]] = []

        # --------------------------------------------------------
        # Strategy 1: Layout extraction
        # --------------------------------------------------------

        try:
            text = page.extract_text(  # type: ignore[attr-defined]
                extraction_mode="layout",
                layout_mode_space_vertically=False,
                layout_mode_strip_rotated=False,
            ) or ""

            candidates.append(
                ("layout", text)
            )

        except Exception:
            logger.debug(
                "PDF layout extraction failed",
                exc_info=True,
            )

        # --------------------------------------------------------
        # Strategy 2: Plain extraction with different spacing
        # --------------------------------------------------------

        for width in self.PLAIN_SPACE_WIDTHS:

            try:
                text = page.extract_text(  # type: ignore[attr-defined]
                    space_width=width,
                ) or ""

                candidates.append(
                    (
                        f"plain_space_width_{int(width)}",
                        text,
                    )
                )

            except Exception:
                logger.debug(
                    "PDF plain extraction failed | "
                    "space_width=%s",
                    width,
                    exc_info=True,
                )

        # --------------------------------------------------------
        # No extraction strategy succeeded
        # --------------------------------------------------------

        if not candidates:
            raise FileParsingError(
                "No PDF text extraction strategy succeeded."
            )

        # --------------------------------------------------------
        # Normalize candidate text
        # --------------------------------------------------------

        normalized = [
            (
                name,
                self._normalize_text(text),
            )
            for name, text in candidates
        ]

        non_empty = [
            item
            for item in normalized
            if item[1]
        ]

        if not non_empty:
            return "", "no_text"

        # --------------------------------------------------------
        # Select best candidate
        # --------------------------------------------------------

        best_strategy, best_text = min(
            non_empty,
            key=lambda item: self._fragmentation_score(
                item[1]
            ),
        )

        # IMPORTANT:
        #
        # Caller expects:
        #
        # raw_text, strategy = self._extract_page(page)
        #
        # Therefore return:
        #
        # text first
        # strategy second
        #
        return best_text, best_strategy

    # ============================================================
    # Fragmentation score
    # ============================================================

    @staticmethod
    def _fragmentation_score(
        text: str,
    ) -> float:

        tokens = text.split()

        if not tokens:
            return 0.0

        single_fragment_count = sum(
            1
            for token in tokens
            if len(token) == 1
            and token.isalpha()
            and token not in {"a", "A", "I"}
        )

        very_short_fragment_count = sum(
            1
            for token in tokens
            if 1 < len(token) <= 3
            and token.isalpha()
        )

        bad_punctuation_spacing = len(
            re.findall(
                r"[A-Za-z]\s+[,.;:!?)]",
                text,
            )
        )

        return (
            single_fragment_count * 5.0
            + very_short_fragment_count * 0.15
            + bad_punctuation_spacing * 1.5
        ) / max(len(tokens), 1)

    # ============================================================
    # Text normalization
    # ============================================================

    @staticmethod
    def _normalize_text(
        text: str,
    ) -> str:

        if not text:
            return ""

        text = unicodedata.normalize(
            "NFKC",
            text,
        )

        for value in (
            "\u200b",
            "\u200c",
            "\u200d",
            "\ufeff",
        ):
            text = text.replace(
                value,
                "",
            )

        text = text.replace(
            "\u00a0",
            " ",
        )

        # Bullet glyphs from fonts without a ToUnicode map come out as DEL.
        text = text.replace(
            "\x7f",
            "\u2022",
        )

        # Other C0 controls (except tab/newline/CR) carry no text and are
        # rejected by post-parse validation, so drop them here.
        text = _CONTROL_CHARS.sub(
            "",
            text,
        )

        text = text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        lines: list[str] = []

        for raw_line in text.split("\n"):

            line = re.sub(
                r"[ \t]+",
                " ",
                raw_line,
            ).strip()

            lines.append(line)

        return "\n".join(lines).strip()

    # ============================================================
    # Metadata
    # ============================================================

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        reader: PdfReader,
        pages: list[dict],
        strategies: Iterable[str],
        warnings: list[dict[str, str]],
    ) -> dict:

        metadata: dict = {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "pdf",
            "file_size_bytes": file_path.stat().st_size,
            "page_count": len(pages),
            "pages": pages,
            "extraction_strategies": sorted(
                set(strategies)
            ),
            "warnings": warnings,
        }

        pdf_header = getattr(
            reader,
            "pdf_header",
            None,
        )

        if pdf_header:
            metadata["pdf_header"] = str(
                pdf_header
            )

        # --------------------------------------------------------
        # PDF document metadata
        # --------------------------------------------------------

        document_metadata = getattr(
            reader,
            "metadata",
            None,
        )

        if document_metadata:

            metadata["document_metadata"] = {
                "title": getattr(
                    document_metadata,
                    "title",
                    None,
                ),
                "author": getattr(
                    document_metadata,
                    "author",
                    None,
                ),
                "subject": getattr(
                    document_metadata,
                    "subject",
                    None,
                ),
                "creator": getattr(
                    document_metadata,
                    "creator",
                    None,
                ),
                "producer": getattr(
                    document_metadata,
                    "producer",
                    None,
                ),
                "creation_date": str(
                    getattr(
                        document_metadata,
                        "creation_date",
                        None,
                    )
                )
                if getattr(
                    document_metadata,
                    "creation_date",
                    None,
                )
                else None,
                "modification_date": str(
                    getattr(
                        document_metadata,
                        "modification_date",
                        None,
                    )
                )
                if getattr(
                    document_metadata,
                    "modification_date",
                    None,
                )
                else None,
            }

        return metadata