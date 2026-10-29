from __future__ import annotations

from ..context import PostSecurityContext

from . import (
    phase_a_injection,
    phase_b_references,
    phase_c_poisoning,
)


class Stage5Pipeline:

    def execute(
        self,
        context: PostSecurityContext,
    ) -> PostSecurityContext:

        if context is None:
            raise ValueError(
                "PostSecurityContext cannot be None."
            )

        # ----------------------------------------------------------
        # Phase A — Prompt injection
        # ----------------------------------------------------------

        context = phase_a_injection.execute(
            context
        )

        # ----------------------------------------------------------
        # Phase B — Source references
        # ----------------------------------------------------------

        context = phase_b_references.execute(
            context
        )

        # ----------------------------------------------------------
        # Phase C — Knowledge poisoning
        # ----------------------------------------------------------

        context = phase_c_poisoning.execute(
            context
        )

        return context