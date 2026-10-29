import tempfile
from pathlib import Path

from app.knowledge.security.stage_2.constants import (
    PHASE_EXTRACTION,
)
from app.knowledge.security.stage_2.context import (
    ArchiveValidationContext,
)
from app.knowledge.security.stage_2.exceptions import (
    WorkspaceCreationError,
)


def create_secure_workspace(
    context: ArchiveValidationContext,
) -> Path:
    """
    Create an isolated temporary extraction workspace.

    The workspace belongs only to this archive-processing run.
    """

    context.current_phase = PHASE_EXTRACTION
    context.current_check = "workspace_creation"

    try:
        workspace = Path(
            tempfile.mkdtemp(
                prefix=f"stage2_{context.document_id}_"
            )
        ).resolve()

        if not workspace.exists():
            raise RuntimeError(
                "Temporary workspace was not created."
            )

        if not workspace.is_dir():
            raise RuntimeError(
                "Temporary workspace is not a directory."
            )

        context.extraction_workspace = workspace

        return workspace

    except WorkspaceCreationError:
        raise

    except Exception as exc:
        raise WorkspaceCreationError(
            (
                f"Unable to create extraction workspace for "
                f"'{context.original_filename}'."
            ),
            phase=PHASE_EXTRACTION,
            check="workspace_creation",
            code="WORKSPACE_CREATION_FAILED",
            details={
                "document_id": context.document_id,
            },
        ) from exc