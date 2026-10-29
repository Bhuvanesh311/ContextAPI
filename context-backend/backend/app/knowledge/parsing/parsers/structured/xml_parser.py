from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as DefusedET

from app.knowledge.parsing.engine.base import BaseParser
from app.knowledge.parsing.enums import ParserFormat
from app.knowledge.parsing.exceptions import (
    FileParsingError,
    SourceFileNotFoundError,
)
from app.knowledge.parsing.schemas import NormalizedDocument, ParsingRequest


logger = logging.getLogger(__name__)


class XMLParser(BaseParser):
   

    parser_name = "xml_parser"
    supported_extensions = (".xml",)

    MAX_FILE_SIZE_BYTES = 256 * 1024 * 1024
    MAX_DOCUMENT_DEPTH = 100
    MAX_DOCUMENT_NODES = 2_000_000
    MAX_ATTRIBUTES_PER_ELEMENT = 10_000
    MAX_TEXT_SIZE = 16 * 1024 * 1024
    MAX_ROOT_KEYS = 100_000

    def parse(
        self,
        file_path: Path,
        request: ParsingRequest,
    ) -> NormalizedDocument:
        self._validate_input(file_path, request)

        try:
            warnings: list[dict[str, str]] = []

            root, strategy = self._extract_xml(
                file_path=file_path,
            )

            structure = self._validate_structure(
                root=root,
            )

            data = self._normalize_tree(
                root=root,
            )

            content = self._serialize_content(data)

            metadata = self._build_metadata(
                file_path=file_path,
                root=root,
                structure=structure,
                strategy=strategy,
                warnings=warnings,
            )

            return NormalizedDocument(
                document_id=request.document_id,
                file_name=file_path.name,
                source_format=ParserFormat.XML,
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
                "XML parsing failed | file=%s | document=%s",
                file_path.name,
                request.document_id,
            )
            raise FileParsingError(
                f"Failed to parse XML: {file_path.name}"
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
                "XML parser received unsupported extension: "
                f"{file_path.suffix or '<none>'}"
            )

        if request.detected_format != ParserFormat.XML:
            raise FileParsingError(
                "XML parser received a non-XML detected format."
            )

        file_size = file_path.stat().st_size

        if file_size <= 0:
            raise FileParsingError(
                f"XML file is empty: {file_path.name}"
            )

        if file_size > cls.MAX_FILE_SIZE_BYTES:
            raise FileParsingError(
                f"XML file exceeds parser limit of "
                f"{cls.MAX_FILE_SIZE_BYTES} bytes: {file_path.name}"
            )

    # Secure extraction

    @classmethod
    def _extract_xml(
        cls,
        *,
        file_path: Path,
    ) -> tuple[Any, str]:
        try:
            tree = DefusedET.parse(file_path)
            root = tree.getroot()

            if root is None:
                raise FileParsingError(
                    f"XML document has no root element: {file_path.name}"
                )

            return root, "defusedxml_elementtree"

        except FileParsingError:
            raise

        except Exception as exc:
            raise FileParsingError(
                f"Invalid or unsafe XML structure in {file_path.name}"
            ) from exc

    # Structural validation

    @classmethod
    def _validate_structure(
        cls,
        *,
        root: Any,
    ) -> dict[str, int]:
        stats = {
            "node_count": 0,
            "maximum_depth": 0,
            "attribute_count": 0,
            "text_characters": 0,
            "element_count": 0,
        }

        stack: list[tuple[Any, int]] = [(root, 0)]

        while stack:
            element, depth = stack.pop()

            stats["node_count"] += 1
            stats["element_count"] += 1
            stats["maximum_depth"] = max(
                stats["maximum_depth"],
                depth,
            )

            if stats["node_count"] > cls.MAX_DOCUMENT_NODES:
                raise FileParsingError(
                    "XML document exceeds the maximum supported node count "
                    f"of {cls.MAX_DOCUMENT_NODES}."
                )

            if depth > cls.MAX_DOCUMENT_DEPTH:
                raise FileParsingError(
                    "XML document exceeds the maximum supported nesting "
                    f"depth of {cls.MAX_DOCUMENT_DEPTH}."
                )

            attribute_count = len(element.attrib)
            stats["attribute_count"] += attribute_count

            if attribute_count > cls.MAX_ATTRIBUTES_PER_ELEMENT:
                raise FileParsingError(
                    "XML element exceeds the maximum supported attribute "
                    f"count of {cls.MAX_ATTRIBUTES_PER_ELEMENT}."
                )

            text = element.text or ""
            tail = element.tail or ""

            stats["text_characters"] += len(text) + len(tail)

            if stats["text_characters"] > cls.MAX_TEXT_SIZE:
                raise FileParsingError(
                    "XML document exceeds the maximum supported extracted "
                    f"text size of {cls.MAX_TEXT_SIZE} characters."
                )

            for child in reversed(list(element)):
                stack.append((child, depth + 1))

        return stats

    # Normalization

    @classmethod
    def _normalize_tree(
        cls,
        *,
        root: Any,
    ) -> dict[str, Any]:
       

        return {
            cls._qualified_tag(root): cls._element_to_value(root)
        }

    @classmethod
    def _element_to_value(
        cls,
        element: Any,
    ) -> Any:
        attributes = {
            f"@{cls._qualified_attribute_name(name)}": cls._normalize_text(value)
            for name, value in element.attrib.items()
        }

        children = list(element)

        text = cls._normalize_text(element.text or "")

        if not children:
            if attributes:
                if text:
                    attributes["#text"] = text
                return attributes

            return text

        result: dict[str, Any] = dict(attributes)

        for child in children:
            key = cls._qualified_tag(child)
            value = cls._element_to_value(child)

            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(value)
            else:
                result[key] = value

        if text:
            result["#text"] = text

        return result

    @staticmethod
    def _normalize_text(
        value: str,
    ) -> str:
        return (
            value.replace("\r\n", "\n")
            .replace("\r", "\n")
        )

    @staticmethod
    def _qualified_tag(
        element: Any,
    ) -> str:
        """
        Preserve namespace information instead of silently dropping it.

        ElementTree represents namespaced tags as:
            {namespace-uri}local-name

        They are normalized to:
            namespace-uri:local-name
        """

        return XMLParser._normalize_qname(element.tag)

    @staticmethod
    def _qualified_attribute_name(
        name: str,
    ) -> str:
        return XMLParser._normalize_qname(name)

    @staticmethod
    def _normalize_qname(
        name: str,
    ) -> str:
        if name.startswith("{") and "}" in name:
            namespace, local_name = name[1:].split("}", 1)
            return f"{namespace}:{local_name}"

        return name

    @staticmethod
    def _serialize_content(
        data: dict[str, Any],
    ) -> str:
        return json.dumps(
            data,
            indent=4,
            ensure_ascii=False,
            sort_keys=False,
        )

    # Metadata

    @classmethod
    def _build_metadata(
        cls,
        *,
        file_path: Path,
        root: Any,
        structure: dict[str, int],
        strategy: str,
        warnings: list[dict[str, str]],
    ) -> dict[str, Any]:
        root_tag = cls._qualified_tag(root)

        metadata: dict[str, Any] = {
            "file_name": file_path.name,
            "file_extension": file_path.suffix.lower(),
            "parser": cls.parser_name,
            "format": "xml",
            "file_size_bytes": file_path.stat().st_size,
            "structure": "hierarchical",
            "root_tag": root_tag,
            "node_count": structure["node_count"],
            "element_count": structure["element_count"],
            "maximum_depth": structure["maximum_depth"],
            "attribute_count": structure["attribute_count"],
            "text_characters": structure["text_characters"],
            "extraction_strategies": [strategy],
            "warnings": warnings,
        }

        return metadata
