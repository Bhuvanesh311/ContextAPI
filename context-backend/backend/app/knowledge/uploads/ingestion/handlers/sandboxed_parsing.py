import os
import tempfile
import logging
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock

from app.core.config import settings
from app.core.enums import IngestionStage
from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.result import IngestionStageResult
from app.knowledge.parsing.enums import ParserFormat, ParserStatus
from app.knowledge.parsing.schemas import ParsingRequest
from app.knowledge.parsing.orchestrator import ParsingOrchestrator
from app.knowledge.parsing.sandbox.limits import DEFAULT_SANDBOX_LIMITS
from app.knowledge.parsing.sandbox.manager import SandboxManager

logger = logging.getLogger(__name__)

# Per worker process (each Celery child has its own pool).
SANDBOX_POOL_SIZE = int(os.getenv("CONTEXTAPI_SANDBOX_POOL_SIZE", "1"))
SANDBOX_IMAGE = os.getenv(
    "CONTEXTAPI_PARSER_SANDBOX_IMAGE",
    "contextapi/parser-sandbox:latest",
)
SANDBOX_WORKSPACE_ROOT = Path(tempfile.gettempdir()) / "contextapi" / "parser-sandbox"

_sandbox_manager: SandboxManager | None = None
_parsing_orchestrator: ParsingOrchestrator | None = None
_parsing_lock = Lock()

def get_parsing_orchestrator() -> ParsingOrchestrator:
    global _sandbox_manager
    global _parsing_orchestrator

    if _parsing_orchestrator is not None:
        return _parsing_orchestrator

    with _parsing_lock:
        if _parsing_orchestrator is not None:
            return _parsing_orchestrator

        logger.info(
            "Initializing ingestion sandbox parsing infrastructure",
            extra={
                "pool_size": SANDBOX_POOL_SIZE,
                "image": SANDBOX_IMAGE,
                "workspace_root": str(SANDBOX_WORKSPACE_ROOT),
            },
        )

        _sandbox_manager = SandboxManager(
            pool_size=SANDBOX_POOL_SIZE,
            image=SANDBOX_IMAGE,
            workspace_root=SANDBOX_WORKSPACE_ROOT,
            limits=DEFAULT_SANDBOX_LIMITS,
        )

        _sandbox_manager.initialize()

        _parsing_orchestrator = ParsingOrchestrator(
            sandbox_manager=_sandbox_manager,
        )

        logger.info("Ingestion sandbox parsing infrastructure initialized successfully")
        return _parsing_orchestrator


class SandboxedParsingHandler:
    def execute(self, context: IngestionContext) -> IngestionStageResult:
        document = context.document
        document_version = context.document_version
        run = context.run

        quarantine_bucket = document_version.quarantine_bucket
        source_object_key = document_version.quarantine_object_key

        if not quarantine_bucket or not source_object_key:
            return IngestionStageResult(
                success=False,
                error_message="Document version missing quarantine bucket or object key."
            )

        extension = (
            document_version.file_extension
            or Path(document_version.file_name).suffix
            or ""
        ).strip().lower()

        if extension and not extension.startswith("."):
            extension = f".{extension}"

        checkpoint = dict(run.checkpoint_data or {})
        parser_format_value = checkpoint.get("parser_format")
        
        if not parser_format_value:
            return IngestionStageResult(
                success=False,
                error_message="Parser format not resolved in checkpoint."
            )
            
        detected_format = ParserFormat(parser_format_value)

        parsed_bucket = document_version.parsed_bucket or settings.MINIO_PARSED_BUCKET
        parsed_object_key = document_version.parsed_object_key or (
            f"projects/{document.project_id}/"
            f"documents/{document.document_id}/"
            f"versions/{document_version.document_version_id}/"
            f"parsed.json"
        )
        
        document_version.parsed_bucket = parsed_bucket
        document_version.parsed_object_key = parsed_object_key
        context.db.flush()

        request = ParsingRequest(
            document_id=document.document_id,
            project_id=document.project_id,
            upload_id=(document.upload_id or run.ingestion_run_id),
            original_filename=document_version.file_name,
            extension=extension,
            mime_type=document_version.mime_type,
            detected_format=detected_format,
            size_bytes=document_version.file_size,
            checksum=document_version.sha256_hash,
            quarantine_bucket=quarantine_bucket,
            source_object_key=source_object_key,
            parsed_bucket=parsed_bucket,
            parsed_object_key=parsed_object_key,
            status=ParserStatus.READY_FOR_PARSING,
        )

        logger.info(
            "Sandboxed parsing started",
            extra={
                "ingestion_run_id": run.ingestion_run_id,
                "document_id": document.document_id,
                "document_version_id": document_version.document_version_id,
                "extension": extension,
                "detected_format": detected_format.value,
                "quarantine_bucket": quarantine_bucket,
                "source_object_key": source_object_key,
            },
        )

        parser = get_parsing_orchestrator()
        result = parser.parse(request)

        if not result.success:
            error_message = result.error_message or "Sandboxed parsing failed."
            logger.error(
                "Sandboxed parsing returned failure",
                extra={
                    "ingestion_run_id": run.ingestion_run_id,
                    "document_id": document.document_id,
                    "parser": result.parser_name,
                    "error": error_message,
                },
            )
            return IngestionStageResult(
                success=False,
                error_message=error_message
            )

        parsed_document = result.document

        checkpoint.update({
            "stage": IngestionStage.SANDBOXED_PARSING.value,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "parser_name": result.parser_name,
            "parsed": True,
            "parsed_document": (
                parsed_document.model_dump(mode="json")
                if parsed_document is not None
                else None
            ),
        })

        logger.info(
            "Sandboxed parsing completed successfully",
            extra={
                "ingestion_run_id": run.ingestion_run_id,
                "document_id": document.document_id,
                "parser": result.parser_name,
            },
        )

        return IngestionStageResult(
            success=True,
            checkpoint_data=checkpoint
        )
