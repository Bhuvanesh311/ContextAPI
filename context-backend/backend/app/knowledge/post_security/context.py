from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .findings import FindingsCollection


@dataclass(slots=True)
class PostSecurityContext:

    # ------------------------------------------------------------------
    # Parsed artifact content
    # ------------------------------------------------------------------

    document: str

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    references: list[str] = field(
        default_factory=list
    )

    # ------------------------------------------------------------------
    # Generated during Stage 4
    # ------------------------------------------------------------------

    normalized_document: str = ""

    findings: FindingsCollection = field(
        default_factory=FindingsCollection
    )

    # ------------------------------------------------------------------
    # Security evaluation
    # ------------------------------------------------------------------

    risk_score: float = 0.0

    is_valid: bool = True

    # ------------------------------------------------------------------
    # Expected upstream identity / provenance
    #
    # These values come from PostgreSQL / the ingestion run, NOT from
    # the untrusted parsed artifact.
    # ------------------------------------------------------------------

    expected_document_id: str | None = None
    expected_project_id: str | None = None
    expected_document_version_id: str | None = None
    expected_file_name: str | None = None
    expected_source_sha256: str | None = None
    expected_source_format: str | None = None
    expected_mime_type: str | None = None
    expected_parser_name: str | None = None

    # ------------------------------------------------------------------
    # Shared stage attributes
    # ------------------------------------------------------------------

    attributes: dict[str, Any] = field(
        default_factory=dict
    )

    def add_attribute(
        self,
        key: str,
        value: Any,
    ) -> None:

        self.attributes[key] = value

    def get_attribute(
        self,
        key: str,
        default: Any = None,
    ) -> Any:

        return self.attributes.get(
            key,
            default,
        )

    def invalidate(self) -> None:
        self.is_valid = False

    def increase_risk(
        self,
        score: float,
    ) -> None:

        self.risk_score += score

    def add_finding(
        self,
        finding,
    ) -> None:

        self.findings.add(finding)