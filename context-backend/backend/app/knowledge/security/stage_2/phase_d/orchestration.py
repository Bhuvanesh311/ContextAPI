from collections.abc import Callable

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ChildRegistrationError,
    ChildQueueError,
)
from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)
from app.knowledge.security.stage_2.phase_d.registration import (
    build_child_contexts,
)
from app.knowledge.security.stage_2.phase_d.routing import (
    assign_child_route,
)


PersistCallback = Callable[
    [ChildFileContext],
    str,
]

QueueCallback = Callable[
    [ChildFileContext],
    None,
]


def persist_child(
    child: ChildFileContext,
    persist_callback: PersistCallback,
) -> ChildFileContext:
    """
    Persist one extracted child.

    Real infrastructure callback is responsible for:

        generate document ID
            ↓
        upload to quarantine
            ↓
        register Document in PostgreSQL
    """

    try:
        document_id = persist_callback(
            child
        )

        if not document_id:
            raise ChildRegistrationError(
                (
                    f"Persistence callback returned no "
                    f"document ID for "
                    f"'{child.original_filename}'."
                ),
                phase="child_orchestration",
                check="child_persistence",
                code="CHILD_DOCUMENT_ID_MISSING",
            )

        child.document_id = document_id

        # The real adapter normally sets these itself.
        # These assignments keep the orchestration contract explicit.
        child.registered = True
        child.stored = True

        return child

    except ChildRegistrationError:
        raise

    except Exception as exc:
        raise ChildRegistrationError(
            (
                f"Unable to persist extracted child "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_persistence",
            code="CHILD_PERSISTENCE_FAILED",
            details={
                "relative_path": child.relative_path,
                "parent_document_id": (
                    child.parent_document_id
                ),
            },
        ) from exc


def queue_child(
    child: ChildFileContext,
    queue_callback: QueueCallback,
) -> ChildFileContext:

    if not child.registered:
        raise ChildQueueError(
            (
                f"Cannot queue '{child.original_filename}' "
                f"before registration."
            ),
            phase="child_orchestration",
            check="child_queue",
            code="CHILD_NOT_REGISTERED",
        )

    if not child.stored:
        raise ChildQueueError(
            (
                f"Cannot queue '{child.original_filename}' "
                f"before quarantine storage."
            ),
            phase="child_orchestration",
            check="child_queue",
            code="CHILD_NOT_STORED",
        )

    if not child.next_stage:
        raise ChildQueueError(
            (
                f"No validation route exists for "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_queue",
            code="CHILD_ROUTE_MISSING",
        )

    try:
        queue_callback(
            child
        )

        child.queued = True

        return child

    except ChildQueueError:
        raise

    except Exception as exc:
        raise ChildQueueError(
            (
                f"Unable to queue extracted child "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_queue",
            code="CHILD_QUEUE_FAILED",
            details={
                "document_id": child.document_id,
                "next_stage": child.next_stage,
            },
        ) from exc


def orchestrate_children(
    context: ArchiveValidationContext,
    *,
    persist_callback: PersistCallback,
    queue_callback: QueueCallback,
) -> list[ChildFileContext]:
    """
    Phase D:

        extracted metadata
              ↓
        build child context
              ↓
        persist child
          ├─ allocate DOC ID
          ├─ store in quarantine
          └─ register PostgreSQL
              ↓
        assign route
              ↓
        queue child
    """

    children = build_child_contexts(
        context
    )

    completed: list[ChildFileContext] = []

    for child in children:

        persist_child(
            child,
            persist_callback,
        )

        assign_child_route(
            child
        )

        queue_child(
            child,
            queue_callback,
        )

        completed.append(
            child
        )

    return completed