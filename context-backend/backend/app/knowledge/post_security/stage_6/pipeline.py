from __future__ import annotations

from ..providers.ollama import (
    OllamaSecurityVerificationProvider,
)
from .contracts import VerificationResult
from .phase_a_candidates import CandidateGenerationPhase
from .phase_b_ai_verification import AIVerificationPhase
from .phase_c_decision import (
    DecisionPhase,
    DecisionResult,
)


class Stage6Pipeline:

    def __init__(self) -> None:

        self._candidate_phase = CandidateGenerationPhase()

        self._verification_phase = AIVerificationPhase(
            provider=OllamaSecurityVerificationProvider()
        )

        self._decision_phase = DecisionPhase()

    def execute(
        self,
        findings: list[object],
    ) -> DecisionResult:

        candidates = self._candidate_phase.execute(
            findings
        )

        verification_results: list[
            VerificationResult
        ] = self._verification_phase.execute(
            candidates
        )

        decision = self._decision_phase.execute(
            verification_results
        )

        return decision