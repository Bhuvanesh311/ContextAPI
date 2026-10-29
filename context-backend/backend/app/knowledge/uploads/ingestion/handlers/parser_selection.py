import logging
from datetime import datetime, timezone
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult

logger = logging.getLogger(__name__)

class ParserSelectionHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        # Parser selection is inherently handled by the ParsingOrchestrator 
        # in the next stage based on the resolved parser_format.
        
        checkpoint = dict(context.run.checkpoint_data or {})
        
        parser_format = checkpoint.get("parser_format")
        if not parser_format:
            return IngestionStageResult(
                success=False,
                error_message="Cannot select parser without an identified format."
            )
            
        checkpoint.update({
            "stage": IngestionStage.PARSER_SELECTION.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        
        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
