from __future__ import annotations

from ..context import PostSecurityContext

from . import (
    phase_a_contract,
    phase_b_completeness,
    phase_c_structure,
    phase_d_normalization,
)


def execute(
    context: PostSecurityContext,
) -> PostSecurityContext:

    # --------------------------------------------------------------
    # Phase A
    # Contract / identity / provenance
    # --------------------------------------------------------------

    context = phase_a_contract.execute(
        context
    )

    if not context.is_valid:
        return context

    # --------------------------------------------------------------
    # Phase B
    # Completeness / parser statistics
    # --------------------------------------------------------------

    context = phase_b_completeness.execute(
        context
    )

    if not context.is_valid:
        return context

    # --------------------------------------------------------------
    # Phase C
    # Structural / resource / Unicode safety
    # --------------------------------------------------------------

    context = phase_c_structure.execute(
        context
    )

    if not context.is_valid:
        return context

    # --------------------------------------------------------------
    # Phase D
    # Conservative normalization
    # --------------------------------------------------------------

    context = phase_d_normalization.execute(
        context
    )

    if not context.is_valid:
        return context

    # --------------------------------------------------------------
    # Final Stage 4 invariant
    # --------------------------------------------------------------

    if not context.normalized_document.strip():

        context.invalidate()

    return context