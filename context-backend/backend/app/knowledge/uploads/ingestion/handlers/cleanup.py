import logging
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class CleanupHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        logger.info(
            "Cleanup stage running",
            extra={"ingestion_run_id": context.run.ingestion_run_id}
        )
        
        # In original orchestrator, cleanup was a no-op (return).
        # We can preserve this behavior or add actual cleanup if needed later.
        
        checkpoint = dict(context.run.checkpoint_data or {})
        checkpoint.update({
            "stage": IngestionStage.CLEANUP.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
