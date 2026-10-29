from __future__ import annotations

import csv
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


class CSVParser(BaseParser):
    
    parser_name = "csv_parser"
    supported_extensions = (".csv",)

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_ROWS = 1_000_000
    MAX_COLUMNS = 10_000
    MAX_FIELD_SIZE = 16 * 1024 * 1024
    MAX_LINE_LENGTH = 16 * 1024 * 1024

    DIALECT_CANDIDATES = (",", ";", "\t", "|")

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            rows, columns, dialect, strategy = self._extract_rows(
                file_path=file_path,
                warnings=warnings,
            )

            content = self._normalize_content(rows)

            metadata = self._build_metadata(
                file_path=file_path,
                columns=columns,
                row_count=len(rows),
                dialect=dialect,
                strategy=strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.CSV,
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
                "CSV parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse CSV: {file_path.name}"
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
                "CSV parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.CSV:
            raise FileParsingError(
                "CSV parser received a non-CSV detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"CSV file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"CSV file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Extraction

    @classmethod
    def _extract_rows(
        cls,
        *,
        file_path: Path,
        warnings: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[str], str, str]:
        try:
            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                sample = file.read(min(cls.MAX_LINE_LENGTH, 1024 * 1024))

            if not sample.strip():
                raise FileParsingError(
                    f"CSV contains no usable content: {file_path.name}"
                )

            delimiter = cls._detect_delimiter(sample)

            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                reader = csv.reader(
                    file,
                    delimiter=delimiter,
                    quotechar='"',
                    doublequote=True,
                    strict=True,
                )

                try:
                    header = next(reader)
                except StopIteration:
                    raise FileParsingError(
                        f"CSV has no header row: {file_path.name}"
                    )

                columns = cls._normalize_headers(
                    header=header,
                    file_name=file_path.name,
                )

                rows: list[dict[str, str]] = []

                for row_number, raw_row in enumerate(reader, start=2):
                    if len(rows) >= cls.MAX_ROWS:
                        raise FileParsingError(
                            f"CSV exceeds maximum row count of "
                            f"{cls.MAX_ROWS}: {file_path.name}"
                        )

                    if len(raw_row) != len(columns):
                        if len(raw_row) > len(columns):
                            raise FileParsingError(
                                f"CSV row {row_number} contains "
                                f"{len(raw_row)} fields but header contains "
                                f"{len(columns)}: {file_path.name}"
                            )

                        raise FileParsingError(
                            f"CSV row {row_number} contains "
                            f"{len(raw_row)} fields but header contains "
                            f"{len(columns)}: {file_path.name}"
                        )

                    normalized_row: dict[str, str] = {}

                    for column, value in zip(columns, raw_row):
                        if len(value) > cls.MAX_FIELD_SIZE:
                            raise FileParsingError(
                                f"CSV field exceeds maximum field size at "
                                f"row {row_number}: {file_path.name}"
                            )

                        normalized_row[column] = (
                            value.replace("\r\n", "\n")
                            .replace("\r", "\n")
                        )

                    rows.append(normalized_row)

            if not rows:
                warnings.append(
                    {
                        "code": "CSV_NO_DATA_ROWS",
                        "severity": "WARNING",
                        "message": "CSV contains a header but no data rows.",
                    }
                )

            strategy = (
                "csv_reader"
                if delimiter == ","
                else "csv_reader_with_controlled_delimiter_detection"
            )

            return rows, columns, delimiter, strategy

        except FileParsingError:
            raise

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"CSV is not valid UTF-8: {file_path.name}"
            ) from exc

        except csv.Error as exc:
            raise FileParsingError(
                f"Invalid CSV structure: {file_path.name}"
            ) from exc

        except OSError as exc:
            raise FileParsingError(
                f"Unable to read CSV: {file_path.name}"
            ) from exc

    @classmethod
    def _detect_delimiter(
        cls,
        sample: str,
    ) -> str:
       

        first_nonempty = next(
            (
                line
                for line in sample.splitlines()
                if line.strip()
            ),
            "",
        )

        if not first_nonempty:
            raise FileParsingError("CSV contains no usable header.")

        candidates: list[tuple[int, int, str]] = []

        for delimiter in cls.DIALECT_CANDIDATES:
            try:
                rows = list(
                    csv.reader(
                        sample.splitlines(),
                        delimiter=delimiter,
                        quotechar='"',
                        doublequote=True,
                        strict=True,
                    )
                )
            except csv.Error:
                continue

            if not rows:
                continue

            widths = [
                len(row)
                for row in rows[:50]
                if row
            ]

            if not widths:
                continue

            header_width = widths[0]

            if header_width <= 1:
                continue

            consistency = sum(
                1 for width in widths if width == header_width
            )

            candidates.append(
                (
                    consistency,
                    header_width,
                    delimiter,
                )
            )

        if not candidates:
            return ","

        candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2] == ",",
            ),
            reverse=True,
        )

        return candidates[0][2]

    @classmethod
    def _normalize_headers(
        cls,
        *,
        header: list[str],
        file_name: str,
    ) -> list[str]:
        if not header:
            raise FileParsingError(
                f"CSV has an empty header row: {file_name}"
            )

        if len(header) > cls.MAX_COLUMNS:
            raise FileParsingError(
                f"CSV exceeds maximum column count of "
                f"{cls.MAX_COLUMNS}: {file_name}"
            )

        columns = [
            cls._normalize_header(column)
            for column in header
        ]

        if any(not column for column in columns):
            raise FileParsingError(
                f"CSV contains an empty column name: {file_name}"
            )

        if len(columns) != len(set(columns)):
            raise FileParsingError(
                f"CSV contains duplicate column names after normalization: "
                f"{file_name}"
            )

        return columns

    # Normalization

    @staticmethod
    def _normalize_header(
        value: str | None,
    ) -> str:
        if value is None:
            return ""

        return value.strip()

    @staticmethod
    def _normalize_content(
        rows: list[dict[str, str]],
    ) -> str:
        # One line per row, each value labelled with its column:
        #   sku: A200 | item: copper wire | stock: 320
        # Every chunk then explains itself (the splitter cuts between rows),
        # which reads and embeds far better than indented JSON, whose
        # whitespace and punctuation also failed the evidence quality check.
        return "\n".join(
            " | ".join(
                f"{column}: {' '.join(str(value or '').split())}"
                for column, value in row.items()
            )
            for row in rows
        )

    # Metadata

    @staticmethod
    def _build_metadata(
        *,
        file_path: Path,
        columns: list[str],
        row_count: int,
        dialect: str,
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        return {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": CSVParser.parser_name,
            "format": "csv",
            "file_size_bytes": file_path.stat().st_size,
            "row_count": row_count,
            "column_count": len(columns),
            "columns": columns,
            "delimiter": (
                "\\t" if dialect == "\t" else dialect
            ),
            "structure": "tabular",
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }
