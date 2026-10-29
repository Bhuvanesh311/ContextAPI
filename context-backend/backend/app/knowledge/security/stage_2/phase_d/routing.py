from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)


STAGE_ONE = "stage_1"


def determine_child_route(
    child: ChildFileContext,
) -> str:
    """
    Every extracted child must re-enter Stage 1.

    `is_archive_candidate` is only metadata/hinting and MUST NOT
    be used to bypass universal validation.
    """

    return STAGE_ONE


def assign_child_route(
    child: ChildFileContext,
) -> ChildFileContext:

    child.next_stage = (
        determine_child_route(child)
    )

    return child