from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


@dataclass(slots=True, frozen=True)
class Candidate:
    identifier: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class CandidateGenerationPhase:

    def execute(
        self,
        findings: list[Any],
    ) -> list[Candidate]:

        candidates: list[Candidate] = []
        seen: set[str] = set()

        for finding in findings:

            identifier = self._build_identifier(
                finding
            )

            if identifier in seen:
                continue

            seen.add(identifier)

            candidates.append(
                Candidate(
                    identifier=identifier,
                    content=finding,
                    metadata={
                        "stage": "stage_6",
                        "phase": "candidate_generation",
                    },
                )
            )

        return candidates

    @staticmethod
    def _build_identifier(
        finding: Any,
    ) -> str:

        code = str(
            getattr(
                finding,
                "code",
                "",
            )
        )

        title = str(
            getattr(
                finding,
                "title",
                "",
            )
        )

        message = str(
            getattr(
                finding,
                "message",
                "",
            )
        )

        severity = str(
            getattr(
                finding,
                "severity",
                "",
            )
        )

        canonical = "|".join(
            (
                code,
                title,
                message,
                severity,
            )
        )

        digest = sha256(
            canonical.encode("utf-8")
        ).hexdigest()[:24]

        return f"candidate_{digest}"