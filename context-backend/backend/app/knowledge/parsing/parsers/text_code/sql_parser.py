from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import expressions as exp

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import NormalizedDocument, ParsingRequest


logger = logging.getLogger(__name__)


class SQLParser(BaseParser):
    

    parser_name = "sql_parser"
    supported_extensions = (".sql",)

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_LINES = 5_000_000
    MAX_LINE_LENGTH = 16 * 1024 * 1024
    MAX_STATEMENTS = 1_000_000
    MAX_TABLE_REFERENCES_PER_STATEMENT = 100_000
    MAX_COLUMN_REFERENCES_PER_STATEMENT = 250_000


    SQL_DIALECT: str | None = None

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            raw_content, extraction_strategy = self._extract_sql(
                file_path=file_path,
            )

            content, lines = self._normalize_content(
                raw_content=raw_content,
            )

            statements = self._parse_statements(
                content=content,
                warnings=warnings,
            )

            analysis = self._analyze_statements(
                statements=statements,
            )

            metadata = self._build_metadata(
                file_path=file_path,
                lines=lines,
                analysis=analysis,
                strategy=extraction_strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.SQL,
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
                "SQL parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse SQL file: {file_path.name}"
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
                "SQL parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.SQL:
            raise FileParsingError(
                "SQL parser received a non-SQL detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"SQL file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"SQL file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Extraction

    @staticmethod
    def _extract_sql(
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
                    f"SQL file contains no content: {file_path.name}"
                )

            return content, "utf8_text_sqlglot"

        except FileParsingError:
            raise

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"SQL file is not valid UTF-8: {file_path.name}"
            ) from exc

        except OSError as exc:
            raise FileParsingError(
                f"Unable to read SQL file: {file_path.name}"
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
                f"SQL file exceeds the maximum supported line count "
                f"of {cls.MAX_LINES}."
            )

        for line_number, line in enumerate(lines, start=1):
            if len(line) > cls.MAX_LINE_LENGTH:
                raise FileParsingError(
                    "SQL line exceeds maximum supported length "
                    f"({cls.MAX_LINE_LENGTH}) at line {line_number}."
                )

        return content, lines

    # SQL parsing

    @classmethod
    def _parse_statements(
        cls,
        *,
        content: str,
        warnings: list[dict[str, str]],
    ) -> list[exp.Expression]:
        try:
            statements = sqlglot.parse(
                content,
                read=cls.SQL_DIALECT,
            )

        except sqlglot.errors.ParseError as exc:
            raise FileParsingError(
                "SQL syntax parsing failed: "
                f"{exc}"
            ) from exc

        except Exception as exc:
            raise FileParsingError(
                "SQL structural parsing failed."
            ) from exc

        if len(statements) > cls.MAX_STATEMENTS:
            raise FileParsingError(
                f"SQL file exceeds the maximum supported statement count "
                f"of {cls.MAX_STATEMENTS}."
            )

        if not statements and content.strip():
            warnings.append(
                {
                    "code": "SQL_NO_STATEMENTS",
                    "severity": "WARNING",
                    "message": (
                        "SQL file contains non-whitespace content but no "
                        "parseable SQL statements were produced."
                    ),
                }
            )

        return statements

    # Structural analysis

    @classmethod
    def _analyze_statements(
        cls,
        *,
        statements: list[exp.Expression],
    ) -> dict[str, Any]:
        statement_metadata: list[dict[str, Any]] = []
        statement_type_counts: dict[str, int] = {}

        all_tables: set[str] = set()
        all_columns: set[str] = set()

        for index, statement in enumerate(statements, start=1):
            statement_type = statement.__class__.__name__.lower()
            statement_sql = statement.sql(
                pretty=False,
            )

            table_names: list[str] = []
            column_names: list[str] = []

            for table in statement.find_all(exp.Table):
                table_name = table.sql(pretty=False)

                if table_name not in table_names:
                    table_names.append(table_name)

                all_tables.add(table_name)

                if len(table_names) > cls.MAX_TABLE_REFERENCES_PER_STATEMENT:
                    raise FileParsingError(
                        "SQL statement exceeds the maximum supported table "
                        "reference count."
                    )

            for column in statement.find_all(exp.Column):
                column_name = column.sql(pretty=False)

                if column_name not in column_names:
                    column_names.append(column_name)

                all_columns.add(column_name)

                if len(column_names) > cls.MAX_COLUMN_REFERENCES_PER_STATEMENT:
                    raise FileParsingError(
                        "SQL statement exceeds the maximum supported column "
                        "reference count."
                    )

            statement_type_counts[statement_type] = (
                statement_type_counts.get(statement_type, 0) + 1
            )

            statement_metadata.append(
                {
                    "index": index,
                    "type": statement_type,
                    "sql": statement_sql,
                    "tables": table_names,
                    "columns": column_names,
                }
            )

        return {
            "statements": statement_metadata,
            "statement_count": len(statement_metadata),
            "statement_type_counts": statement_type_counts,
            "tables": sorted(all_tables),
            "columns": sorted(all_columns),
        }

    # Metadata

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        lines: list[str],
        analysis: dict[str, Any],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        if not analysis["statements"] and lines:
            warnings.append(
                {
                    "code": "SQL_NO_PARSEABLE_STATEMENTS",
                    "severity": "WARNING",
                    "message": (
                        "No SQL statements were produced by the structural "
                        "parser."
                    ),
                }
            )

        return {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "sql",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "sql_statements",
            "line_count": len(lines),
            "statement_count": analysis["statement_count"],
            "statement_type_counts": (
                analysis["statement_type_counts"]
            ),
            "statements": analysis["statements"],
            "tables": analysis["tables"],
            "columns": analysis["columns"],
            "table_count": len(analysis["tables"]),
            "column_count": len(analysis["columns"]),
            "dialect": cls.SQL_DIALECT or "generic",
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }
