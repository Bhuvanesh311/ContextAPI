from collections.abc import Callable

from app.knowledge.security.stage_2.exceptions import (
    StageTwoStorageError,
)
from app.knowledge.security.stage_2.phase_d.context import (
    ChildFileContext,
)


StoreChildCallable = Callable[
    [ChildFileContext],
    str,
]


def store_child(
    child: ChildFileContext,
    store_callback: StoreChildCallable,
) -> ChildFileContext:
    """
    Persist an extracted child into quarantine storage.

    The callback returns the resulting object/storage key.
    """

    if not child.registered:
        raise StageTwoStorageError(
            (
                f"Cannot store '{child.original_filename}' "
                f"before child registration."
            ),
            phase="child_orchestration",
            check="child_storage",
            code="CHILD_NOT_REGISTERED",
        )

    if not child.document_id:
        raise StageTwoStorageError(
            (
                f"Child document ID is unavailable for "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_storage",
            code="CHILD_DOCUMENT_ID_MISSING",
        )

    try:

        storage_key = store_callback(
            child
        )

        if not storage_key:
            raise StageTwoStorageError(
                (
                    f"Storage returned no object key for "
                    f"'{child.original_filename}'."
                ),
                phase="child_orchestration",
                check="child_storage",
                code="CHILD_STORAGE_KEY_MISSING",
            )

        child.storage_key = str(
            storage_key
        )

        child.stored = True

        return child

    except StageTwoStorageError:
        raise

    except Exception as exc:
        raise StageTwoStorageError(
            (
                f"Unable to store extracted child "
                f"'{child.original_filename}'."
            ),
            phase="child_orchestration",
            check="child_storage",
            code="CHILD_STORAGE_FAILED",
            details={
                "document_id": (
                    child.document_id
                ),
                "parent_document_id": (
                    child.parent_document_id
                ),
            },
        ) from exc