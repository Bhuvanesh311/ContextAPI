from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import NormalizedDocument, ParsingRequest


logger = logging.getLogger(__name__)


class YAMLParser(BaseParser):
   

    parser_name = "yaml_parser"

    supported_extensions = (
        ".yaml",
        ".yml",
    )

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_DOCUMENT_DEPTH = 100
    MAX_DOCUMENT_NODES = 2_000_000
    MAX_OBJECT_KEYS = 1_000_000
    MAX_ARRAY_ITEMS = 1_000_000
    MAX_STRING_SIZE = 16 * 1024 * 1024

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            data, strategy = self._extract_yaml(
                file_path=file_path,
            )

            structure = self._validate_structure(
                value=data,
            )

            if data is None:
                warnings.append(
                    {
                        "code": "YAML_NULL_ROOT",
                        "severity": "WARNING",
                        "message": "YAML document contains a null root value.",
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
                source_format=ParserFormat.YAML,
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
                "YAML parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse YAML: {file_path.name}"
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
                "YAML parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.YAML:
            raise FileParsingError(
                "YAML parser received a non-YAML detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"YAML file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"YAML file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Secure extraction

    @classmethod
    def _extract_yaml(
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
                yaml_content = file.read()

            if not yaml_content.strip():
                raise FileParsingError(
                    f"YAML file contains no document content: {file_path.name}"
                )
            data = yaml.safe_load(yaml_content)

            return data, "pyyaml_safe_load"

        except FileParsingError:
            raise

        except UnicodeDecodeError as exc:
            raise FileParsingError(
                f"YAML file is not valid UTF-8: {file_path.name}"
            ) from exc

        except yaml.YAMLError as exc:
            raise FileParsingError(
                f"Invalid or unsafe YAML syntax in {file_path.name}: {exc}"
            ) from exc

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
            "string_characters": 0,
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
                    "YAML document exceeds the maximum supported node count "
                    f"of {cls.MAX_DOCUMENT_NODES}."
                )

            if depth > cls.MAX_DOCUMENT_DEPTH:
                raise FileParsingError(
                    "YAML document exceeds the maximum supported nesting "
                    f"depth of {cls.MAX_DOCUMENT_DEPTH}."
                )

            if isinstance(current, dict):
                stats["object_count"] += 1
                stats["object_key_count"] += len(current)

                if stats["object_key_count"] > cls.MAX_OBJECT_KEYS:
                    raise FileParsingError(
                        "YAML document exceeds the maximum supported total "
                        f"object-key count of {cls.MAX_OBJECT_KEYS}."
                    )

                for key, child in current.items():
                    cls._validate_mapping_key(key)
                    stack.append((child, depth + 1))

            elif isinstance(current, list):
                stats["array_count"] += 1
                stats["array_item_count"] += len(current)

                if stats["array_item_count"] > cls.MAX_ARRAY_ITEMS:
                    raise FileParsingError(
                        "YAML document exceeds the maximum supported total "
                        f"array-item count of {cls.MAX_ARRAY_ITEMS}."
                    )

                for child in reversed(current):
                    stack.append((child, depth + 1))

            elif isinstance(current, str):
                stats["string_characters"] += len(current)

                if len(current) > cls.MAX_STRING_SIZE:
                    raise FileParsingError(
                        "YAML contains a scalar string exceeding the maximum "
                        f"supported size of {cls.MAX_STRING_SIZE} characters."
                    )

        return stats

    @staticmethod
    def _validate_mapping_key(key: Any) -> None:
   
        if not isinstance(key, str):
            raise FileParsingError(
                "YAML contains a non-string mapping key; "
                "structured normalization requires string keys."
            )

    # Normalization

    @classmethod
    def _normalize_content(
        cls,
        data: Any,
    ) -> str:
   

        try:
            return json.dumps(
                data,
                indent=4,
                ensure_ascii=False,
                sort_keys=False,
                allow_nan=False,
            )

        except (TypeError, ValueError) as exc:
            raise FileParsingError(
                "Parsed YAML contains values that cannot be normalized "
                "to canonical JSON."
            ) from exc

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
            "format": "yaml",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "hierarchical",
            "root_type": root_type,
            "node_count": structure["node_count"],
            "object_count": structure["object_count"],
            "array_count": structure["array_count"],
            "object_key_count": structure["object_key_count"],
            "array_item_count": structure["array_item_count"],
            "maximum_depth": structure["maximum_depth"],
            "string_characters": structure["string_characters"],
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
