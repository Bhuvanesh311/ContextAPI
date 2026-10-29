from __future__ import annotations

import json
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


class JSONParser(BaseParser):
    

    parser_name = "json_parser"
    supported_extensions = (".json",)

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024


    MAX_DOCUMENT_DEPTH = 100
    MAX_OBJECT_KEYS = 1_000_000
    MAX_ARRAY_ITEMS = 1_000_000
    MAX_DOCUMENT_NODES = 2_000_000

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            data, strategy = self._extract_json(
                file_path=file_path,
            )

            structure = self._validate_structure(
                value=data,
            )

            if data is None:
                warnings.append(
                    {
                        "code": "JSON_NULL_ROOT",
                        "severity": "WARNING",
                        "message": "JSON document contains a null root value.",
                    }
                )

            content = self._normalize_content(data)

            metadata = self._build_metadata(
                file_path=file_path,
                data=data,
                structure=structure,
                strategy=strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.JSON,
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
                "JSON parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse JSON: {file_path.name}"
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
                "JSON parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.JSON:
            raise FileParsingError(
                "JSON parser received a non-JSON detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"JSON file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"JSON file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Extraction

    @classmethod
    def _extract_json(
        cls,
        *,
        file_path: Path,
    ) -> tuple[Any, str]:
        try:
            with file_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                data = json.load(
                    file,
                    object_pairs_hook=cls._strict_object_pairs,
                    parse_constant=cls._reject_non_standard_constant,
                )

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"JSON file is not valid UTF-8: {file_path.name}"
            ) from exc

        except json.JSONDecodeError as exc:
            raise FileParsingError(
                f"Invalid JSON syntax in {file_path.name}: "
                f"line {exc.lineno}, column {exc.colno}"
            ) from exc

        except ValueError as exc:
            raise FileParsingError(
                f"Invalid JSON content in {file_path.name}: {exc}"
            ) from exc

        return data, "json_stdlib_strict"

    # Strict JSON semantics

    @staticmethod
    def _strict_object_pairs(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for key, value in pairs:
            if key in result:
                raise ValueError(
                    f"duplicate JSON object key: {key!r}"
                )

            result[key] = value

        return result

    @staticmethod
    def _reject_non_standard_constant(
        constant: str,
    ) -> Any:
        raise ValueError(
            f"non-standard JSON numeric constant is not allowed: {constant}"
        )

    # Structural/resource validation

    @classmethod
    def _validate_structure(
        cls,
        *,
        value: Any,
    ) -> dict[str, int]:
       

        stats = {
            "node_count": 0,
            "object_count": 0,
            "array_count": 0,
            "object_key_count": 0,
            "array_item_count": 0,
            "maximum_depth": 0,
        }

        stack: list[tuple[Any, int]] = [(value, 0)]

        while stack:
            current, depth = stack.pop()

            stats["node_count"] += 1
            stats["maximum_depth"] = max(
                stats["maximum_depth"],
                depth,
            )

            if stats["node_count"] > cls.MAX_DOCUMENT_NODES:
                raise FileParsingError(
                    "JSON document exceeds the maximum supported node count "
                    f"of {cls.MAX_DOCUMENT_NODES}."
                )

            if depth > cls.MAX_DOCUMENT_DEPTH:
                raise FileParsingError(
                    "JSON document exceeds the maximum supported nesting "
                    f"depth of {cls.MAX_DOCUMENT_DEPTH}."
                )

            if isinstance(current, dict):
                stats["object_count"] += 1
                stats["object_key_count"] += len(current)

                if stats["object_key_count"] > cls.MAX_OBJECT_KEYS:
                    raise FileParsingError(
                        "JSON document exceeds the maximum supported total "
                        f"object-key count of {cls.MAX_OBJECT_KEYS}."
                    )

                for child in reversed(list(current.values())):
                    stack.append((child, depth + 1))

            elif isinstance(current, list):
                stats["array_count"] += 1
                stats["array_item_count"] += len(current)

                if stats["array_item_count"] > cls.MAX_ARRAY_ITEMS:
                    raise FileParsingError(
                        "JSON document exceeds the maximum supported total "
                        f"array-item count of {cls.MAX_ARRAY_ITEMS}."
                    )

                for child in reversed(current):
                    stack.append((child, depth + 1))

        return stats

    # Normalization

    @staticmethod
    def _normalize_content(
        data: Any,
    ) -> str:
    

        return json.dumps(
            data,
            indent=4,
            ensure_ascii=False,
            sort_keys=False,
            allow_nan=False,
        )

    # Metadata

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        data: Any,
        structure: dict[str, int],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        root_type = cls._root_type(data)

        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "json",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "hierarchical",
            "root_type": root_type,
            "node_count": structure["node_count"],
            "object_count": structure["object_count"],
            "array_count": structure["array_count"],
            "object_key_count": structure["object_key_count"],
            "array_item_count": structure["array_item_count"],
            "maximum_depth": structure["maximum_depth"],
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }

        if isinstance(data, dict):
            metadata["root_key_count"] = len(data)
            metadata["root_keys"] = list(data.keys())

        elif isinstance(data, list):
            metadata["root_item_count"] = len(data)

        return metadata

    @staticmethod
    def _root_type(
        data: Any,
    ) -> str:
        if data is None:
            return "null"

        if isinstance(data, bool):
            return "boolean"

        if isinstance(data, int) and not isinstance(data, bool):
            return "integer"

        if isinstance(data, float):
            return "number"

        if isinstance(data, str):
            return "string"

        if isinstance(data, list):
            return "array"

        if isinstance(data, dict):
            return "object"

        return type(data).__name__
