import logging
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class CompletedHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        logger.info(
            "Ingestion completed",
            extra={"ingestion_run_id": context.run.ingestion_run_id}
        )
        
        checkpoint = dict(context.run.checkpoint_data or {})
        checkpoint.update({
            "stage": IngestionStage.COMPLETED.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })

        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
