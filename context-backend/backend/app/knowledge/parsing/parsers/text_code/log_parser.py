from __future__ import annotations

import logging
import re
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


class LogParser(BaseParser):
   

    parser_name = "log_parser"
    supported_extensions = (".log",)

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_LINES = 5_000_000
    MAX_LINE_LENGTH = 16 * 1024 * 1024

    _LEVEL_RE = re.compile(
        r"(?<![A-Z0-9_])"
        r"(TRACE|DEBUG|INFO|NOTICE|WARN|WARNING|ERROR|ERR|CRITICAL|FATAL)"
        r"(?![A-Z0-9_])",
        re.IGNORECASE,
    )

    _TIMESTAMP_RE = re.compile(
        r"""
        ^\s*
        (?:
            # ISO-8601 / common application logs
            \d{4}-\d{2}-\d{2}
            [T\s]
            \d{2}:\d{2}:\d{2}
            (?:[.,]\d{1,9})?
            (?:Z|[+-]\d{2}:?\d{2})?
        |
            # Slash-separated date
            \d{4}/\d{2}/\d{2}
            [T\s]
            \d{2}:\d{2}:\d{2}
            (?:[.,]\d{1,9})?
            (?:Z|[+-]\d{2}:?\d{2})?
        |
            # Day-first date
            \d{2}-\d{2}-\d{4}
            [T\s]
            \d{2}:\d{2}:\d{2}
            (?:[.,]\d{1,9})?
        |
            \d{2}/\d{2}/\d{4}
            [T\s]
            \d{2}:\d{2}:\d{2}
            (?:[.,]\d{1,9})?
        |
            # Time-only application logs
            \d{2}:\d{2}:\d{2}
            (?:[.,]\d{1,9})?
        )
        """,
        re.VERBOSE,
    )

    _CONTINUATION_RE = re.compile(
        r"^(?:\s+|"
        r"(?:Traceback \(most recent call last\):)|"
        r"(?:Caused by:)|"
        r"(?:at\s+\S+)|"
        r"(?:\.\.\.)"
        r")"
    )

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            raw_content, strategy = self._extract_log(
                file_path=file_path,
            )

            content, lines = self._normalize_content(
                raw_content=raw_content,
            )

            analysis = self._analyze_lines(lines)

            if not lines:
                warnings.append(
                    {
                        "code": "LOG_NO_LINES",
                        "severity": "WARNING",
                        "message": "Log contains no logical lines.",
                    }
                )

            if analysis["empty_line_count"] > 0:
                warnings.append(
                    {
                        "code": "LOG_EMPTY_LINES",
                        "severity": "INFO",
                        "message": (
                            "Log contains one or more empty logical lines."
                        ),
                    }
                )

            if analysis["timestamped_line_count"] == 0:
                warnings.append(
                    {
                        "code": "LOG_TIMESTAMP_NOT_DETECTED",
                        "severity": "INFO",
                        "message": (
                            "No recognized timestamp prefix was detected; "
                            "the log is retained as raw normalized text."
                        ),
                    }
                )

            metadata = self._build_metadata(
                file_path=file_path,
                content=content,
                lines=lines,
                analysis=analysis,
                strategy=strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.LOG,
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
                "Log parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse log file: {file_path.name}"
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
                "Log parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.LOG:
            raise FileParsingError(
                "Log parser received a non-LOG detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"Log file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"Log file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Extraction

    @classmethod
    def _extract_log(
        cls,
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
                    f"Log file contains no content: {file_path.name}"
                )

            for line_number, line in enumerate(
                content.splitlines(),
                start=1,
            ):
                if len(line) > cls.MAX_LINE_LENGTH:
                    raise FileParsingError(
                        "Log line exceeds maximum supported length "
                        f"({cls.MAX_LINE_LENGTH}) at line {line_number}: "
                        f"{file_path.name}"
                    )

            return content, "utf8_text"

        except FileParsingError:
            raise

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"Log file is not valid UTF-8: {file_path.name}"
            ) from exc

        except OSError as exc:
            raise FileParsingError(
                f"Unable to read log file: {file_path.name}"
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

        logical_lines = content.split("\n")

        if logical_lines and logical_lines[-1] == "":
            logical_lines = logical_lines[:-1]

        if len(logical_lines) > cls.MAX_LINES:
            raise FileParsingError(
                "Log file exceeds the maximum supported line count of "
                f"{cls.MAX_LINES}."
            )

        return content, logical_lines

    # Lightweight analysis

    @classmethod
    def _analyze_lines(
        cls,
        lines: list[str],
    ) -> dict[str, Any]:
        counts = {
            "trace_count": 0,
            "debug_count": 0,
            "info_count": 0,
            "notice_count": 0,
            "warning_count": 0,
            "error_count": 0,
            "critical_count": 0,
        }

        timestamped_line_count = 0
        continuation_line_count = 0
        level_detected_line_count = 0
        empty_line_count = 0

        for line in lines:
            if not line.strip():
                empty_line_count += 1
                continue

            if cls._TIMESTAMP_RE.search(line):
                timestamped_line_count += 1

            if cls._CONTINUATION_RE.search(line):
                continuation_line_count += 1

            matches = cls._LEVEL_RE.findall(line)

            if matches:
                level_detected_line_count += 1

            for match in matches:
                level = match.upper()

                if level == "TRACE":
                    counts["trace_count"] += 1
                elif level == "DEBUG":
                    counts["debug_count"] += 1
                elif level == "INFO":
                    counts["info_count"] += 1
                elif level == "NOTICE":
                    counts["notice_count"] += 1
                elif level in {"WARN", "WARNING"}:
                    counts["warning_count"] += 1
                elif level in {"ERROR", "ERR"}:
                    counts["error_count"] += 1
                elif level in {"CRITICAL", "FATAL"}:
                    counts["critical_count"] += 1

        return {
            **counts,
            "timestamped_line_count": timestamped_line_count,
            "timestamp_detected": timestamped_line_count > 0,
            "level_detected_line_count": level_detected_line_count,
            "continuation_line_count": continuation_line_count,
            "empty_line_count": empty_line_count,
            "first_event": lines[0] if lines else None,
            "last_event": lines[-1] if lines else None,
        }

    # Metadata

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        content: str,
        lines: list[str],
        analysis: dict[str, Any],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "log",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "line_oriented_text",
            "line_count": len(lines),
            "empty_lines": analysis["empty_line_count"],
            "timestamp_detected": analysis["timestamp_detected"],
            "timestamped_line_count": analysis["timestamped_line_count"],
            "level_detected_line_count": (
                analysis["level_detected_line_count"]
            ),
            "continuation_line_count": (
                analysis["continuation_line_count"]
            ),
            "first_event": analysis["first_event"],
            "last_event": analysis["last_event"],
            "trace_count": analysis["trace_count"],
            "debug_count": analysis["debug_count"],
            "info_count": analysis["info_count"],
            "notice_count": analysis["notice_count"],
            "warning_count": analysis["warning_count"],
            "error_count": analysis["error_count"],
            "critical_count": analysis["critical_count"],
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }
