from __future__ import annotations

from typing import Protocol

from .contracts import VerificationResult
from .phase_a_candidates import Candidate
from ..enums import VerificationStatus


class SecurityVerificationProvider(Protocol):

    def verify(
        self,
        candidate: Candidate,
    ) -> VerificationResult:
        ...


class RuleBasedSecurityVerificationProvider:

    def verify(
        self,
        candidate: Candidate,
    ) -> VerificationResult:

        finding = candidate.content

        if finding is None:
            return VerificationResult(
                candidate=candidate,
                status=VerificationStatus.FAILED,
                confidence=1.0,
                reason="Security finding is missing.",
            )

        code = str(
            getattr(
                finding,
                "code",
                "",
            )
        ).upper()

        message = str(
            getattr(
                finding,
                "message",
                "",
            )
        ).strip()

        if not code and not message:
            return VerificationResult(
                candidate=candidate,
                status=VerificationStatus.FAILED,
                confidence=1.0,
                reason=(
                    "Security finding does not contain "
                    "verifiable evidence."
                ),
            )

        return VerificationResult(
            candidate=candidate,
            status=VerificationStatus.FAILED,
            confidence=0.0,
            reason=(
                "No semantic AI verifier is configured. "
                "The finding requires review rather than "
                "being treated as verified."
            ),
        )


class AIVerificationPhase:

    def __init__(
        self,
        provider: SecurityVerificationProvider | None = None,
    ) -> None:

        self._provider = provider

    def execute(
        self,
        candidates: list[Candidate],
    ) -> list[VerificationResult]:

        results: list[VerificationResult] = []

        for candidate in candidates:

            try:
                result = self._provider.verify(
                    candidate
                ) if self._provider else (
                    RuleBasedSecurityVerificationProvider()
                    .verify(candidate)
                )

            except Exception:
                results.append(
                    VerificationResult(
                        candidate=candidate,
                        status=VerificationStatus.FAILED,
                        confidence=0.0,
                        reason=(
                            "Security verification "
                            "failed."
                        ),
                    )
                )
                continue

            results.append(
                VerificationResult(
                    candidate=result.candidate,
                    status=result.status,
                    confidence=self._normalize_confidence(
                        result.confidence
                    ),
                    reason=result.reason,
                )
            )

        return results

    @staticmethod
    def _normalize_confidence(
        confidence: float,
    ) -> float:

        try:
            value = float(confidence)
        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )