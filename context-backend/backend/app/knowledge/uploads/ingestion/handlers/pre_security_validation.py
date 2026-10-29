import logging
from datetime import datetime, timezone

from sqlalchemy import event

from app.core.enums import IngestionStage
from app.knowledge.security.presecurityrunner import PreSecurityRunner
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)


class PreSecurityValidationHandler:
    """Execute the existing pre-security validation pipeline."""

    def execute(
        self,
        context: IngestionContext,
    ) -> IngestionStageResult:

        logger.info(
            "Pre-security validation started",
            extra={
                "ingestion_run_id": (
                    context.run.ingestion_run_id
                ),
                "document_id": (
                    context.document.document_id
                ),
            },
        )

        runner = PreSecurityRunner(
            db=context.db,
        )

        result = runner.run(
            document=context.document,
            document_version=context.document_version,
        )

        if not result.success:
            return IngestionStageResult(
                success=False,
                error_message=(
                    "Pre-security validation failed"
                ),
            )

        checkpoint = dict(
            context.run.checkpoint_data or {}
        )

        checkpoint.update(
            {
                "stage": (
                    IngestionStage
                    .PRE_SECURITY_VALIDATION
                    .value
                ),
                "completed_at": (
                    datetime.now(timezone.utc).isoformat()
                ),
                "pre_security": result.to_dict(),
            }
        )

        logger.info(
            "Pre-security validation completed",
            extra={
                "ingestion_run_id": (
                    context.run.ingestion_run_id
                ),
                "document_id": (
                    context.document.document_id
                ),
                "is_archive": result.is_archive,
                "child_document_ids": (
                    result.child_document_ids
                ),
            },
        )

        if result.is_archive:
            from app.knowledge.uploads.models import IngestionRun
            from app.knowledge.uploads.tasks import run_ingestion_task
            
            if result.child_document_ids:
                child_run_ids = [
                    run_id
                    for (run_id,) in context.db.query(IngestionRun.ingestion_run_id).filter(
                        IngestionRun.document_id.in_(result.child_document_ids)
                    )
                ]

                # The child runs are only flushed so far. Queue them once the
                # orchestrator commits this stage: a worker that picked one up
                # before that found no run, crashed, and left it PENDING.
                def dispatch_children(session):
                    for run_id in child_run_ids:
                        run_ingestion_task.delay(run_id)

                event.listen(context.db, "after_commit", dispatch_children, once=True)
            
            checkpoint["archive_completed"] = True

        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint,
        )