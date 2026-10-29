from __future__ import annotations

import json

import yaml
from defusedxml import ElementTree

from app.knowledge.security.stage_3.context import (
    ValidationContext,
)
from app.knowledge.security.stage_3.exceptions import (
    FormatSecurityError,
)

# ============================================================
# JSON Security
# ============================================================

MAX_JSON_DEPTH = 100

MAX_JSON_OBJECTS = 100_000

# ============================================================
# XML Security
# ============================================================

MAX_XML_DEPTH = 100

MAX_XML_ELEMENTS = 100_000

FORBIDDEN_XML_PATTERNS = (
    b"<!DOCTYPE",
    b"<!ENTITY",
)

# ============================================================
# YAML Security
# ============================================================

MAX_YAML_DEPTH = 100

MAX_YAML_DOCUMENTS = 100

MAX_YAML_ALIASES = 128


def validate(
    context: ValidationContext,
) -> None:
    """
    Perform security validation for structured documents.

    Supported:
        - JSON
        - XML
        - YAML
    """

    extension = (
        context.extension.lower()
    )

    # ========================================================
    # JSON Validation
    # ========================================================

    if extension == ".json":

        _validate_json(
            context,
        )

    # ========================================================
    # XML Validation
    # ========================================================

    elif extension == ".xml":

        _validate_xml(
            context,
        )

    # ========================================================
    # YAML Validation
    # ========================================================

    elif extension in {
        ".yaml",
        ".yml",
    }:

        _validate_yaml(
            context,
        )

    elif extension == ".csv":

        _validate_csv(
            context,
        )

    # ========================================================
    # Unsupported Format
    # ========================================================

    else:

        raise FormatSecurityError(
            f"Unsupported structured format '{extension}'.",
            phase="structured_validation",
            check="format_selection",
            code="UNSUPPORTED_STRUCTURED_FORMAT",
        )

    context.security_validated = True


def _validate_json(
    context: ValidationContext,
) -> None:
    """
    Validate JSON documents against security risks that
    could affect ContextAPI's ingestion pipeline.
    """

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:

        with context.file_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            document = json.load(
                file,
            )

    except json.JSONDecodeError as exc:

        raise FormatSecurityError(
            "Invalid JSON document.",
            phase="json_validation",
            check="parser_validation",
            code="INVALID_JSON",
        ) from exc

    # --------------------------------------------------------
    # Maximum Nesting Depth
    # --------------------------------------------------------

    stack = [
        (
            document,
            1,
        )
    ]

    while stack:

        value, depth = stack.pop()

        if depth > MAX_JSON_DEPTH:

            raise FormatSecurityError(
                "JSON nesting depth exceeds the allowed limit.",
                phase="json_validation",
                check="maximum_nesting_depth",
                code="JSON_DEPTH_EXCEEDED",
            )

        if isinstance(
            value,
            dict,
        ):

            stack.extend(
                (
                    child,
                    depth + 1,
                )
                for child in value.values()
            )

        elif isinstance(
            value,
            list,
        ):

            stack.extend(
                (
                    child,
                    depth + 1,
                )
                for child in value
            )

    # --------------------------------------------------------
    # Maximum Object Count
    # --------------------------------------------------------

    object_count = 0

    stack = [document]

    while stack:

        value = stack.pop()

        object_count += 1

        if object_count > MAX_JSON_OBJECTS:

            raise FormatSecurityError(
                "JSON object count exceeds the allowed limit.",
                phase="json_validation",
                check="maximum_object_count",
                code="JSON_OBJECT_LIMIT_EXCEEDED",
            )

        if isinstance(
            value,
            dict,
        ):

            stack.extend(
                value.values()
            )

        elif isinstance(
            value,
            list,
        ):

            stack.extend(
                value,
            )


def _validate_xml(
    context: ValidationContext,
) -> None:
    """
    Validate XML documents against security risks that
    could affect ContextAPI's ingestion pipeline.
    """

    # --------------------------------------------------------
    # Read XML
    # --------------------------------------------------------

    try:

        data = context.file_path.read_bytes()

    except OSError as exc:

        raise FormatSecurityError(
            "Unable to read XML document.",
            phase="xml_validation",
            check="file_read",
            code="XML_READ_FAILED",
        ) from exc

    # --------------------------------------------------------
    # XXE / ENTITY Detection
    # --------------------------------------------------------

    if b"<!DOCTYPE" in data:

        raise FormatSecurityError(
            "DOCTYPE declarations are not allowed.",
            phase="xml_validation",
            check="xxe_detection",
            code="XML_DOCTYPE_DETECTED",
        )

    if b"<!ENTITY" in data:

        raise FormatSecurityError(
            "ENTITY declarations are not allowed.",
            phase="xml_validation",
            check="entity_detection",
            code="XML_ENTITY_DETECTED",
        )

    # --------------------------------------------------------
    # Parser Validation
    # --------------------------------------------------------

    try:

        root = ElementTree.fromstring(
            data,
        )

    except Exception as exc:

        raise FormatSecurityError(
            "Invalid XML document.",
            phase="xml_validation",
            check="parser_validation",
            code="INVALID_XML",
        ) from exc

    # --------------------------------------------------------
    # Maximum Nesting Depth
    # --------------------------------------------------------

    stack = [
        (
            root,
            1,
        )
    ]

    element_count = 0

    while stack:

        element, depth = stack.pop()

        element_count += 1

        if depth > MAX_XML_DEPTH:

            raise FormatSecurityError(
                "XML nesting depth exceeds the allowed limit.",
                phase="xml_validation",
                check="maximum_nesting_depth",
                code="XML_DEPTH_EXCEEDED",
            )

        if element_count > MAX_XML_ELEMENTS:

            raise FormatSecurityError(
                "XML element count exceeds the allowed limit.",
                phase="xml_validation",
                check="maximum_element_count",
                code="XML_ELEMENT_LIMIT_EXCEEDED",
            )

        for child in element:

            stack.append(
                (
                    child,
                    depth + 1,
                )
            )


def _validate_yaml(
    context: ValidationContext,
) -> None:
    """
    Validate YAML documents against security risks that
    could affect ContextAPI's ingestion pipeline.
    """

    # --------------------------------------------------------
    # Parser Validation
    # --------------------------------------------------------

    try:

        with context.file_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            document = yaml.safe_load(
                file,
            )

    except yaml.YAMLError as exc:

        raise FormatSecurityError(
            "Invalid YAML document.",
            phase="yaml_validation",
            check="parser_validation",
            code="INVALID_YAML",
        ) from exc

    # Empty document

    if document is None:
        return

    # --------------------------------------------------------
    # Maximum Nesting Depth
    # --------------------------------------------------------

    stack = [
        (
            document,
            1,
        )
    ]

    object_count = 0

    while stack:

        value, depth = stack.pop()

        object_count += 1

        if depth > MAX_YAML_DEPTH:

            raise FormatSecurityError(
                "YAML nesting depth exceeds the allowed limit.",
                phase="yaml_validation",
                check="maximum_nesting_depth",
                code="YAML_DEPTH_EXCEEDED",
            )

        if object_count > MAX_YAML_DOCUMENTS:

            raise FormatSecurityError(
                "YAML object count exceeds the allowed limit.",
                phase="yaml_validation",
                check="maximum_object_count",
                code="YAML_OBJECT_LIMIT_EXCEEDED",
            )

        if isinstance(
            value,
            dict,
        ):

            stack.extend(
                (
                    child,
                    depth + 1,
                )
                for child in value.values()
            )

        elif isinstance(
            value,
            list,
        ):

            stack.extend(
                (
                    child,
                    depth + 1,
                )
                for child in value
            )

def _validate_csv(
    context: ValidationContext,
) -> None:
    try:
        with context.file_path.open("r", encoding="utf-8-sig") as f:
            for _ in f:
                pass
    except Exception as exc:
        raise FormatSecurityError(
            "Invalid CSV document.",
            phase="format_validation",
            check="csv",
            code="INVALID_CSV",
        ) from exc