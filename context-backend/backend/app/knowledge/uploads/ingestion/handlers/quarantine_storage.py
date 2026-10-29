import logging
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class QuarantineStorageHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        logger.info(
            "Quarantine storage stage acknowledged (already processed synchronously)",
            extra={"ingestion_run_id": context.run.ingestion_run_id}
        )
        
        # We ensure it actually has a quarantine bucket set, just as a sanity check.
        if not context.document_version.quarantine_bucket:
            return IngestionStageResult(
                success=False,
                error_message="Document version does not have a quarantine bucket."
            )
            
        if not context.document_version.quarantine_object_key:
            return IngestionStageResult(
                success=False,
                error_message="Document version does not have a quarantine object key."
            )
        
        checkpoint = dict(context.run.checkpoint_data or {})
        checkpoint.update({
            "stage": IngestionStage.QUARANTINE_STORAGE.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
