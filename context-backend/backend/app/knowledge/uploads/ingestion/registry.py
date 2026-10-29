import importlib
from typing import Protocol, Type
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion_state import STAGE_ORDER
from .context import IngestionContext
from .result import IngestionStageResult

class IngestionStageHandler(Protocol):
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        ...

_HANDLER_MAP = {
    IngestionStage.UPLOAD_RECEIVED: ("app.knowledge.uploads.ingestion.handlers.upload_received", "UploadReceivedHandler"),
    IngestionStage.QUARANTINE_STORAGE: ("app.knowledge.uploads.ingestion.handlers.quarantine_storage", "QuarantineStorageHandler"),
    IngestionStage.PRE_SECURITY_VALIDATION: ("app.knowledge.uploads.ingestion.handlers.pre_security_validation", "PreSecurityValidationHandler"),
    IngestionStage.FORMAT_IDENTIFICATION: ("app.knowledge.uploads.ingestion.handlers.format_identification", "FormatIdentificationHandler"),
    IngestionStage.FORMAT_VALIDATION: ("app.knowledge.uploads.ingestion.handlers.format_validation", "FormatValidationHandler"),
    IngestionStage.PARSER_SELECTION: ("app.knowledge.uploads.ingestion.handlers.parser_selection", "ParserSelectionHandler"),
    IngestionStage.SANDBOXED_PARSING: ("app.knowledge.uploads.ingestion.handlers.sandboxed_parsing", "SandboxedParsingHandler"),
    IngestionStage.POST_PARSE_VALIDATION: ("app.knowledge.uploads.ingestion.handlers.post_parse_validation", "PostParseValidationHandler"),
    IngestionStage.AI_RAG_SECURITY_VALIDATION: ("app.knowledge.uploads.ingestion.handlers.ai_rag_security_validation", "AiRagSecurityValidationHandler"),
    IngestionStage.PERMANENT_STORAGE: ("app.knowledge.uploads.ingestion.handlers.permanent_storage", "PermanentStorageHandler"),
    IngestionStage.CLEANUP: ("app.knowledge.uploads.ingestion.handlers.cleanup", "CleanupHandler"),
    IngestionStage.COMPLETED: ("app.knowledge.uploads.ingestion.handlers.completed", "CompletedHandler"),
}

class IngestionStageRegistry:
    def __init__(self):
        self._handlers: dict[IngestionStage, IngestionStageHandler] = {}
        
        missing_stages = [stage for stage in STAGE_ORDER if stage not in _HANDLER_MAP]
        if missing_stages:
            raise RuntimeError(f"Missing handler registrations for stages: {missing_stages}")

    def get(self, stage: IngestionStage) -> IngestionStageHandler:
        if stage in self._handlers:
            return self._handlers[stage]

        if stage not in _HANDLER_MAP:
            raise RuntimeError(f"No handler registered for ingestion stage: {stage}")

        module_path, class_name = _HANDLER_MAP[stage]
        module = importlib.import_module(module_path)
        handler_class = getattr(module, class_name)
        handler_instance = handler_class()
        self._handlers[stage] = handler_instance
        return handler_instance

registry = IngestionStageRegistry()
