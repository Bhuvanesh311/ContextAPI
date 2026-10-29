from collections.abc import Callable

from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    ChildRegistrationError,
)
from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)


RegisterChildCallable = Callable[
    [ChildFileContext],
    str,
]


def build_child_contexts(
    context: ArchiveValidationContext,
) -> list[ChildFileContext]:
    """
    Convert Phase C extracted metadata into Phase D child
    contexts.

    No database operations occur here.
    """

    children: list[ChildFileContext] = []

    for item in context.extracted_files:

        child = ChildFileContext(
            parent_document_id=(
                context.document_id
            ),
            upload_id=context.upload_id,
            project_id=context.project_id,

            relative_path=(
                item.relative_path
            ),
            source_path=(
                item.absolute_path
            ),

            original_filename=(
                item.filename
            ),
            size=item.size,

            archive_depth=(
                item.archive_depth
            ),

            is_archive_candidate=(
                item.is_archive_candidate
            ),
        )

        children.append(child)

    return children


def register_child(
    child: ChildFileContext,
    register_callback: RegisterChildCallable,
) -> ChildFileContext:
    """
    Register one extracted child through an injected database
    callback.

    The callback must return the created Document ID.
    """

    try:

        document_id = register_callback(
            child
        )

        if not document_id:
            raise ChildRegistrationError(
                (
                    f"Child registration returned no document ID "
                    f"for '{child.original_filename}'."
                ),
                phase="child_orchestration",
                check="child_registration",
                code="CHILD_DOCUMENT_ID_MISSING",
            )

        child.document_id = str(
            document_id
        )

        child.registered = True

        return child

    except ChildRegistrationError:
        raise

    except Exception as exc:
        raise ChildRegistrationError(
            (
                f"Unable to register extracted child "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_registration",
            code="CHILD_REGISTRATION_FAILED",
            details={
                "parent_document_id": (
                    child.parent_document_id
                ),
                "relative_path": (
                    child.relative_path
                ),
            },
        ) from exc