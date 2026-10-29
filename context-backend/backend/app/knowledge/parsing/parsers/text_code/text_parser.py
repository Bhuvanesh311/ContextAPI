from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import NormalizedDocument, ParsingRequest


logger = logging.getLogger(__name__)


class TextParser(BaseParser):
 

    parser_name = "text_parser"
    supported_extensions = (".txt", ".rst", ".tsv")

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_LINES = 5_000_000
    MAX_LINE_LENGTH = 16 * 1024 * 1024

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            raw_content, extraction_strategy = self._extract_text(
                file_path=file_path,
            )

            content, lines = self._normalize_content(
                raw_content=raw_content,
            )

            analysis = self._analyze_lines(
                lines=lines,
                warnings=warnings,
            )

            metadata = self._build_metadata(
                file_path=file_path,
                analysis=analysis,
                strategy=extraction_strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.TXT,
                content=content,
                metadata=metadata,
                page_count=0,
                character_count=len(content),
                word_count=len(content.split()),
                mime_type=request.mime_type,
            )

        except FileParsingError:
            raise

        except Exception as exc:
            logger.exception(
                "Text parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse text file: {file_path.name}"
            ) from exc

    # Validation

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
                "Text parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.TXT:
            raise FileParsingError(
                "Text parser received a non-text detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"Text file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"Text file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Extraction

    @staticmethod
    def _extract_text(
        *,
        file_path: Path,
    ) -> tuple[str, str]:
        try:
            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                content = file.read()

            if not content:
                raise FileParsingError(
                    f"Text file contains no content: {file_path.name}"
                )

            return content, "utf8_text"

        except FileParsingError:
            raise

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"Text file is not valid UTF-8: {file_path.name}"
            ) from exc

        except OSError as exc:
            raise FileParsingError(
                f"Unable to read text file: {file_path.name}"
            ) from exc

    # Normalization

    @classmethod
    def _normalize_content(
        cls,
        *,
        raw_content: str,
    ) -> tuple[str, list[str]]:
     

        content = (
            raw_content
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        lines = content.split("\n")

    
        if lines and lines[-1] == "":
            lines = lines[:-1]

        if len(lines) > cls.MAX_LINES:
            raise FileParsingError(
                f"Text file exceeds the maximum supported line count "
                f"of {cls.MAX_LINES}."
            )

        for line_number, line in enumerate(lines, start=1):
            if len(line) > cls.MAX_LINE_LENGTH:
                raise FileParsingError(
                    "Text line exceeds maximum supported length "
                    f"({cls.MAX_LINE_LENGTH}) at line {line_number}."
                )

        return content, lines

    # Lightweight analysis

    @staticmethod
    def _analyze_lines(
        *,
        lines: list[str],
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        empty_lines = sum(
            1
            for line in lines
            if line == ""
        )

        whitespace_only_lines = sum(
            1
            for line in lines
            if line != "" and not line.strip()
        )

        non_empty_lines = len(lines) - empty_lines

        maximum_line_length = max(
            (len(line) for line in lines),
            default=0,
        )

        first_line = lines[0] if lines else None
        last_line = lines[-1] if lines else None

        if whitespace_only_lines:
            warnings.append(
                {
                    "code": "TEXT_WHITESPACE_ONLY_LINES",
                    "severity": "INFO",
                    "message": (
                        "Text contains whitespace-only logical lines; "
                        "original whitespace was preserved."
                    ),
                }
            )

        return {
            "line_count": len(lines),
            "empty_line_count": empty_lines,
            "whitespace_only_line_count": whitespace_only_lines,
            "non_empty_line_count": non_empty_lines,
            "maximum_line_length": maximum_line_length,
            "first_line": first_line,
            "last_line": last_line,
        }

    # Metadata

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        analysis: dict[str, Any],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "text",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "plain_text",
            "line_count": analysis["line_count"],
            "non_empty_lines": analysis["non_empty_line_count"],
            "empty_lines": analysis["empty_line_count"],
            "whitespace_only_lines": (
                analysis["whitespace_only_line_count"]
            ),
            "maximum_line_length": analysis["maximum_line_length"],
            "first_line": analysis["first_line"],
            "last_line": analysis["last_line"],
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }
