from __future__ import annotations

from dataclasses import dataclass

from ..enums import SecurityDecision, VerificationStatus
from ..findings import FindingSeverity
from .contracts import VerificationResult


@dataclass(slots=True, frozen=True)
class DecisionResult:

    decision: SecurityDecision
    confidence: float
    reason: str


class DecisionPhase:

    def execute(
        self,
        verification_results: list[
            VerificationResult
        ],
    ) -> DecisionResult:

        if not verification_results:

            return DecisionResult(
                decision=SecurityDecision.ALLOW,
                confidence=1.0,
                reason=(
                    "No security findings require "
                    "verification."
                ),
            )

        failed = [
            result
            for result in verification_results
            if result.status
            == VerificationStatus.FAILED
        ]

        verified = [
            result
            for result in verification_results
            if result.status
            == VerificationStatus.VERIFIED
        ]

        # --------------------------------------------------
        # Any verification failure means uncertainty.
        # Do not silently allow.
        # --------------------------------------------------

        if failed:

            confidence = self._confidence(
                verification_results
            )

            return DecisionResult(
                decision=SecurityDecision.REVIEW,
                confidence=confidence,
                reason=(
                    "One or more security findings "
                    "could not be conclusively verified."
                ),
            )

        # --------------------------------------------------
        # All findings were verified.
        # Now evaluate their severity.
        # --------------------------------------------------

        blocking = [
            result
            for result in verified
            if self._is_blocking_finding(
                result
            )
        ]

        if blocking:

            confidence = self._confidence(
                blocking
            )

            return DecisionResult(
                decision=SecurityDecision.BLOCK,
                confidence=confidence,
                reason=(
                    "Verified high or critical security "
                    "findings were detected."
                ),
            )

        # --------------------------------------------------
        # Everything verified and nothing blocking.
        # --------------------------------------------------

        confidence = self._confidence(
            verification_results
        )

        return DecisionResult(
            decision=SecurityDecision.ALLOW,
            confidence=confidence,
            reason=(
                "All security findings were verified "
                "and no blocking condition was confirmed."
            ),
        )

    @staticmethod
    def _is_blocking_finding(
        result: VerificationResult,
    ) -> bool:
    
        finding = result.candidate.content
    
        severity = getattr(
            finding,
            "severity",
            None,
        )
    
        if severity is None:
            return False
    
        severity_value = getattr(
            severity,
            "value",
            severity,
        )
    
        normalized = str(
            severity_value
        ).strip().upper()
    
        return normalized in {
            "HIGH",
            "CRITICAL",
        }
    
    @staticmethod
    def _confidence(
        results: list[
            VerificationResult
        ],
    ) -> float:

        if not results:
            return 1.0

        total = sum(
            max(
                0.0,
                min(
                    1.0,
                    float(result.confidence),
                ),
            )
            for result in results
        )

        return total / len(results)