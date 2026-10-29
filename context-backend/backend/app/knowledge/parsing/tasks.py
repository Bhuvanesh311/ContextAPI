from __future__ import annotations
import os
import logging
import tempfile
from pathlib import Path

from celery import shared_task

from app.knowledge.parsing.enums import ParserStatus
from app.knowledge.parsing.orchestrator import (
    ParsingOrchestrator,
)
from app.knowledge.parsing.schemas import (
    ParsingRequest,
)
from app.knowledge.parsing.sandbox.limits import (
    DEFAULT_SANDBOX_LIMITS,
)
from app.knowledge.parsing.sandbox.manager import (
    SandboxManager,
)

logger = logging.getLogger(__name__)


# Sandbox configuration

# Per worker process (each Celery child has its own pool).
SANDBOX_POOL_SIZE = int(os.getenv("CONTEXTAPI_SANDBOX_POOL_SIZE", "1"))
SANDBOX_IMAGE = os.getenv(
    "CONTEXTAPI_PARSER_SANDBOX_IMAGE",
    "contextapi/parser-sandbox:latest",
)
SANDBOX_WORKSPACE_ROOT = (
    Path(tempfile.gettempdir())
    / "contextapi"
    / "parser-sandbox"
)


# Celery-process-local sandbox manager

_sandbox_manager: SandboxManager | None = None


def _get_sandbox_manager() -> SandboxManager:


    global _sandbox_manager

    if _sandbox_manager is None:
        _sandbox_manager = SandboxManager(
                pool_size=SANDBOX_POOL_SIZE,
                image=SANDBOX_IMAGE,
                workspace_root=SANDBOX_WORKSPACE_ROOT,
                limits=DEFAULT_SANDBOX_LIMITS,
            )

        _sandbox_manager.initialize()

        logger.info(
            "Parsing sandbox manager initialized",
            extra={
                "pool_size": SANDBOX_POOL_SIZE,
                "workspace_root": str(
                    SANDBOX_WORKSPACE_ROOT
                ),
            },
        )

    return _sandbox_manager


# Parsing task

@shared_task(
    name="parsing.parse_document",
    bind=True,
    autoretry_for=(),
)
def parse_document(
    self,
    document_data: dict,
) -> dict:


    document_id = document_data["document_id"]

    logger.info(
        "Parsing task started",
        extra={
            "task_id": self.request.id,
            "document_id": document_id,
        },
    )

    try:
        request = ParsingRequest(
            document_id=document_data["document_id"],
            project_id=document_data["project_id"],
            upload_id=document_data["upload_id"],
            original_filename=document_data[
                "original_filename"
            ],
            extension=document_data["extension"],
            mime_type=document_data["mime_type"],
            detected_format=(
                    "source_code"
                    if document_data["detected_format"]
                    in {
                        "python",
                        "javascript",
                        "typescript",
                        "java",
                        "c",
                        "cpp",
                        "csharp",
                        "go",
                        "rust",
                        "php",
                        "ruby",
                        "swift",
                        "kotlin",
                    }
                    else document_data["detected_format"]
                ),
            size_bytes=document_data["size_bytes"],
            checksum=document_data["checksum"],
            quarantine_bucket=document_data[
                "quarantine_bucket"
            ],
            source_object_key=document_data[
                "source_object_key"
            ],
            status=ParserStatus.READY_FOR_PARSING,
        )

        manager = _get_sandbox_manager()

        orchestrator = ParsingOrchestrator(
            sandbox_manager=manager,
        )

        result = orchestrator.parse(
            request,
        )

        if not result.success:
            logger.warning(
                "Parsing task completed with parser failure",
                extra={
                    "task_id": self.request.id,
                    "document_id": document_id,
                    "parser": result.parser_name,
                    "error": result.error_message,
                },
            )

            return {
                "success": False,
                "document_id": document_id,
                "parser_name": result.parser_name,
                "error_message": result.error_message,
            }

        logger.info(
            "Parsing task completed successfully",
            extra={
                "task_id": self.request.id,
                "document_id": document_id,
                "parser": result.parser_name,
            },
        )

        return {
            "success": True,
            "document_id": document_id,
            "parser_name": result.parser_name,
        }

    except Exception:
        logger.exception(
            "Parsing Celery task failed",
            extra={
                "task_id": self.request.id,
                "document_id": document_id,
            },
        )

        raise
