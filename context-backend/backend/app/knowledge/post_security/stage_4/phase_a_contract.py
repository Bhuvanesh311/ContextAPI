from __future__ import annotations

from typing import Any

from ..constants import (
    CANONICAL_PARSED_DOCUMENT_VERSION,
    MAX_METADATA_KEYS,
    MAX_METADATA_SERIALIZED_BYTES,
    MAX_METADATA_VALUE_STRING_LENGTH,
    PARSER_NAME_METADATA_KEY,
    PARSER_VERSION_METADATA_KEY,
    PROJECT_ID_METADATA_KEY,
    REFERENCES_METADATA_KEY,
    SCHEMA_VERSION_METADATA_KEY,
    SOURCE_SHA256_METADATA_KEY,
)
from ..context import PostSecurityContext
from ..exceptions import ContractValidationError
from ..findings import (
    FindingSeverity,
    SecurityFinding,
)


PHASE_NAME = "stage_4.phase_a_contract"


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    if context is None:
        raise ContractValidationError(
            "Post security context cannot be None."
        )

    _validate_document(context)
    _validate_metadata(context)
    _validate_references(context)
    _validate_identity(context)
    _validate_optional_provenance(context)

    return context


def _add_invalid_contract_finding(
    context: PostSecurityContext,
    *,
    code: str,
    title: str,
    message: str,
    metadata: dict[str, str] | None = None,
) -> None:

    context.invalidate()

    context.findings.add(
        SecurityFinding(
            code=code,
            title=title,
            message=message,
            severity=FindingSeverity.HIGH,
            phase=PHASE_NAME,
            metadata=metadata or {},
        )
    )


def _validate_document(
    context: PostSecurityContext,
) -> None:

    if not isinstance(
        context.document,
        str,
    ):
        raise ContractValidationError(
            "Document must be a string."
        )

    if not context.document.strip():

        _add_invalid_contract_finding(
            context,
            code="PSC001",
            title="Empty Document",
            message="Document content is empty.",
        )


def _validate_metadata(
    context: PostSecurityContext,
) -> None:

    if not isinstance(
        context.metadata,
        dict,
    ):
        raise ContractValidationError(
            "Metadata must be a dictionary."
        )

    if len(context.metadata) > MAX_METADATA_KEYS:

        _add_invalid_contract_finding(
            context,
            code="PSC002",
            title="Metadata Limit Exceeded",
            message=(
                "Parsed artifact metadata contains too many keys."
            ),
        )
        return

    for key, value in context.metadata.items():

        if not isinstance(key, str):

            _add_invalid_contract_finding(
                context,
                code="PSC003",
                title="Invalid Metadata Key",
                message=(
                    "Parsed artifact metadata keys "
                    "must be strings."
                ),
            )
            break

        if (
            isinstance(value, str)
            and len(value)
            > MAX_METADATA_VALUE_STRING_LENGTH
        ):

            _add_invalid_contract_finding(
                context,
                code="PSC004",
                title="Metadata Value Too Large",
                message=(
                    "A parsed metadata string exceeds "
                    "the maximum supported length."
                ),
                metadata={
                    "key": key,
                },
            )
            break

    # Serialize only after structural checks.
    try:
        import json

        metadata_size = len(
            json.dumps(
                context.metadata,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )

    except (TypeError, ValueError) as exc:

        raise ContractValidationError(
            "Parsed metadata cannot be serialized safely."
        ) from exc

    if metadata_size > MAX_METADATA_SERIALIZED_BYTES:

        _add_invalid_contract_finding(
            context,
            code="PSC005",
            title="Metadata Size Exceeded",
            message=(
                "Parsed artifact metadata exceeds "
                "the maximum supported size."
            ),
        )


def _validate_references(
    context: PostSecurityContext,
) -> None:

    if not isinstance(
        context.references,
        list,
    ):
        raise ContractValidationError(
            "References must be a list."
        )

    if len(context.references) > MAX_METADATA_KEYS:

        _add_invalid_contract_finding(
            context,
            code="PSC006",
            title="Reference Limit Exceeded",
            message=(
                "Parsed artifact contains too many references."
            ),
        )
        return

    for index, reference in enumerate(
        context.references
    ):

        if not isinstance(
            reference,
            str,
        ):

            _add_invalid_contract_finding(
                context,
                code="PSC007",
                title="Invalid Reference",
                message=(
                    "Every parsed artifact reference "
                    "must be a string."
                ),
                metadata={
                    "reference_index": str(index),
                },
            )
            continue

        if not reference.strip():

            _add_invalid_contract_finding(
                context,
                code="PSC008",
                title="Empty Reference",
                message=(
                    "Parsed artifact references "
                    "cannot be empty."
                ),
                metadata={
                    "reference_index": str(index),
                },
            )


def _validate_identity(
    context: PostSecurityContext,
) -> None:

    expected_document_id = (
        context.expected_document_id
    )

    if (
        expected_document_id
        and context.get_attribute("document_id")
        and context.get_attribute("document_id")
        != expected_document_id
    ):
        _add_invalid_contract_finding(
            context,
            code="PSC009",
            title="Context Identity Mismatch",
            message=(
                "Post-Security context document identity "
                "does not match the trusted ingestion identity."
            ),
        )

    expected_project_id = (
        context.expected_project_id
    )

    if (
        expected_project_id
        and context.get_attribute("project_id")
        and context.get_attribute("project_id")
        != expected_project_id
    ):
        _add_invalid_contract_finding(
            context,
            code="PSC010",
            title="Project Identity Mismatch",
            message=(
                "Post-Security project identity does not "
                "match the trusted ingestion identity."
            ),
        )


def _validate_optional_provenance(
    context: PostSecurityContext,
) -> None:

    metadata = context.metadata

    schema_version = metadata.get(
        SCHEMA_VERSION_METADATA_KEY
    )

    if (
        schema_version is not None
        and schema_version
        != CANONICAL_PARSED_DOCUMENT_VERSION
    ):

        _add_invalid_contract_finding(
            context,
            code="PSC011",
            title="Unsupported Parsed Schema Version",
            message=(
                "The parsed artifact declares an unsupported "
                "canonical schema version."
            ),
            metadata={
                "schema_version": str(schema_version),
            },
        )

    parser_name = metadata.get(
        PARSER_NAME_METADATA_KEY
    )

    expected_parser_name = (
        context.expected_parser_name
    )

    if (
        parser_name is not None
        and expected_parser_name
        and parser_name != expected_parser_name
    ):

        _add_invalid_contract_finding(
            context,
            code="PSC012",
            title="Parser Identity Mismatch",
            message=(
                "The parser identity recorded in the artifact "
                "does not match the trusted parser identity."
            ),
        )

    source_sha256 = metadata.get(
        SOURCE_SHA256_METADATA_KEY
    )

    expected_sha256 = (
        context.expected_source_sha256
    )

    if (
        source_sha256 is not None
        and expected_sha256
        and source_sha256.lower()
        != expected_sha256.lower()
    ):

        _add_invalid_contract_finding(
            context,
            code="PSC013",
            title="Source Hash Mismatch",
            message=(
                "The parsed artifact source hash does not "
                "match the trusted document version hash."
            ),
        )

    project_id = metadata.get(
        PROJECT_ID_METADATA_KEY
    )

    if (
        project_id is not None
        and context.expected_project_id
        and project_id
        != context.expected_project_id
    ):

        _add_invalid_contract_finding(
            context,
            code="PSC014",
            title="Parsed Project Mismatch",
            message=(
                "The parsed artifact project identity does "
                "not match the trusted document project."
            ),
        )

    # Parser version is currently informational because the existing
    # parser contract does not expose a trusted parser version.
    parser_version = metadata.get(
        PARSER_VERSION_METADATA_KEY
    )

    if (
        parser_version is not None
        and not isinstance(
            parser_version,
            str,
        )
    ):

        _add_invalid_contract_finding(
            context,
            code="PSC015",
            title="Invalid Parser Version",
            message=(
                "Parser version metadata must be a string."
            ),
        )