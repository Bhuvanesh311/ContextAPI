import logging
from pathlib import Path
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class FormatValidationHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        checkpoint = dict(context.run.checkpoint_data or {})
        
        extension = (
            context.document_version.file_extension
            or Path(context.document_version.file_name).suffix
            or ""
        ).strip().lower()
        
        if not extension:
            return IngestionStageResult(
                success=False,
                error_message="Document version does not have a file extension."
            )
            
        parser_format = checkpoint.get("parser_format")
        if not parser_format:
            return IngestionStageResult(
                success=False,
                error_message="No parser format was identified in the previous stage."
            )
            
        checkpoint.update({
            "stage": IngestionStage.FORMAT_VALIDATION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
