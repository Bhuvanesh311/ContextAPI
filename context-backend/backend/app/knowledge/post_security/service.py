from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .context import PostSecurityContext
from .stage_4 import pipeline as stage_4_pipeline
from .stage_5.pipeline import Stage5Pipeline
from .stage_6.pipeline import Stage6Pipeline
from .stage_6.phase_c_decision import DecisionResult
from .enums import SecurityDecision


@dataclass(slots=True)
class PostSecurityResult:

    decision: SecurityDecision
    confidence: float
    reason: str
    context: PostSecurityContext


class PostSecurityService:

    def __init__(self) -> None:
        self._stage5 = Stage5Pipeline()
        self._stage6 = Stage6Pipeline()

    def execute(
        self,
        context: PostSecurityContext,
    ) -> PostSecurityResult:
        

       
        # Stage 4
       

        context = stage_4_pipeline.execute(context)

        if not context.is_valid:
            return PostSecurityResult(
                decision=SecurityDecision.BLOCK,
                confidence=1.0,
                reason="Document rejected during Stage 4 validation.",
                context=context,
            )

       
        # Stage 5
       

        context = self._stage5.execute(context)

       
        # Stage 6
       

        findings = list(context.findings)

        decision: DecisionResult = self._stage6.execute(findings)

        return PostSecurityResult(
            decision=decision.decision,
            confidence=decision.confidence,
            reason=decision.reason,
            context=context,
        )