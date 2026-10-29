import logging
from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.enums import (
    DocumentStatus,
    IngestionRunStatus,
    IngestionStage,
    DocumentVersionStatus,
)
from app.knowledge.cancellation import (
    CANCELLED_CODE,
    CANCELLED_MESSAGE,
    is_cancelled,
)
from app.knowledge.uploads.models import (
    IngestionRun,
    Document,
    DocumentVersion,
)

from app.knowledge.uploads.ingestion_service import (
    get_ingestion_run,
    update_ingestion_stage,
    update_ingestion_status,
    save_ingestion_checkpoint,
    record_ingestion_failure,
)

from app.knowledge.uploads.ingestion_state import (
    get_next_stage,
    is_terminal_stage,
)

from app.knowledge.uploads.ingestion_retry import (
    schedule_retry,
    mark_retry_exhausted,
)

from app.knowledge.uploads.ingestion_failure import (
    classify_failure,
    FailureCategory,
)

from app.knowledge.uploads.ingestion.context import IngestionContext
from app.knowledge.uploads.ingestion.registry import registry
from app.knowledge.processing.services.trigger import (
    KnowledgeProcessingTriggerService,
)

logger = logging.getLogger(__name__)

class IngestionOrchestrator:

    def __init__(self, db: Session):
        self.db = db

    def run(self, ingestion_run_id: str) -> IngestionRun:
        run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

        if run.status == IngestionRunStatus.COMPLETED:
            return run

        if run.status == IngestionRunStatus.CANCELLED:
            return run

        try:
            if not self._start_run(run):
                logger.info(
                    "Ingestion run is already being processed; skipping duplicate task",
                    extra={"ingestion_run_id": ingestion_run_id},
                )
                return run

            while True:
                run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)
                current_stage = run.current_stage

                # Stopped by the user: leave the run as the stop request set it.
                if self._stopped(run):
                    return run

                if is_terminal_stage(current_stage):
                    self._complete_run(run)
                    break

                logger.info(
                    "Executing ingestion stage",
                    extra={
                        "ingestion_run_id": ingestion_run_id,
                        "document_id": run.document_id,
                        "stage": current_stage.value,
                    },
                )

                self._execute_stage(run=run, stage=current_stage)

                run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)
                
                current_checkpoint = dict(run.checkpoint_data or {})
                if current_checkpoint.get("archive_completed"):
                    self._complete_run(run)
                    break
                    
                next_stage = get_next_stage(run.current_stage)

                if next_stage is None:
                    self._complete_run(run)
                    break

                current_checkpoint = dict(run.checkpoint_data or {})
                current_checkpoint.update({
                    "stage": run.current_stage.value,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })

                save_ingestion_checkpoint(
                    db=self.db,
                    ingestion_run_id=ingestion_run_id,
                    checkpoint_data=current_checkpoint,
                )

                update_ingestion_stage(
                    db=self.db,
                    ingestion_run_id=ingestion_run_id,
                    stage=next_stage,
                )

                self.db.commit()

            return get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

        except Exception as exc:
            logger.exception(
                "Ingestion orchestration failed",
                extra={
                    "ingestion_run_id": ingestion_run_id,
                },
            )
            self.db.rollback()
            run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)
            if self._stopped(run):
                return run
            return self._handle_failure(
                ingestion_run_id=ingestion_run_id,
                exception=exc,
            )

    def _stopped(self, run: IngestionRun) -> bool:
        if run.status == IngestionRunStatus.CANCELLED:
            return True
        if not is_cancelled(run.document_version_id):
            return False
        # Flagged before the stop request could record it: record it here.
        self.db.refresh(run)
        if run.status != IngestionRunStatus.CANCELLED:
            run.status = IngestionRunStatus.CANCELLED
            run.error_code = CANCELLED_CODE
            run.error_message = CANCELLED_MESSAGE
            run.next_retry_at = None
            self.db.commit()
        return True

    def _start_run(self, run: IngestionRun) -> bool:
        """
        Claim the run for this task: PENDING/RETRYING -> RUNNING in one
        conditional UPDATE. Returns False when another task already holds it
        (a duplicate message, e.g. re-queued by recovery while still queued).
        """
        if run.status in {IngestionRunStatus.PENDING, IngestionRunStatus.RETRYING}:
            now = datetime.now(timezone.utc)
            claimed = (
                self.db.query(IngestionRun)
                .filter(
                    IngestionRun.ingestion_run_id == run.ingestion_run_id,
                    IngestionRun.status.in_(
                        [IngestionRunStatus.PENDING, IngestionRunStatus.RETRYING]
                    ),
                )
                .update(
                    {
                        IngestionRun.status: IngestionRunStatus.RUNNING,
                        IngestionRun.updated_at: now,
                        IngestionRun.started_at: func.coalesce(IngestionRun.started_at, now),
                    },
                    synchronize_session=False,
                )
            )
            self.db.commit()
            self.db.refresh(run)
            return bool(claimed)

        if run.status == IngestionRunStatus.FAILED:
            raise RuntimeError("Cannot start a permanently failed ingestion run.")

        if run.status == IngestionRunStatus.RUNNING:
            # Runs only start from PENDING or RETRYING (recovery moves a run
            # whose worker died back to RETRYING), so this is a duplicate.
            return False

        raise RuntimeError(f"Unsupported ingestion run status: {run.status}")

    def _execute_stage(self, run: IngestionRun, stage: IngestionStage) -> None:
        handler = registry.get(stage)
        document, document_version = self._get_document_and_version(run)
        
        context = IngestionContext(
            db=self.db,
            run=run,
            document=document,
            document_version=document_version
        )
        
        result = handler.execute(context)
        
        if not result.success:
            raise RuntimeError(result.error_message or f"Stage {stage.value} failed without error message.")
            
        if result.checkpoint_data is not None:
            save_ingestion_checkpoint(
                db=self.db,
                ingestion_run_id=run.ingestion_run_id,
                checkpoint_data=result.checkpoint_data,
            )
            self.db.commit()

    def _get_document_and_version(self, run: IngestionRun) -> tuple[Document, DocumentVersion]:
        document = self.db.query(Document).filter(Document.document_id == run.document_id).first()
        if document is None:
            raise RuntimeError(f"Document not found: {run.document_id}")

        document_version = self.db.query(DocumentVersion).filter(
            DocumentVersion.document_version_id == run.document_version_id
        ).first()

        if document_version is None:
            raise RuntimeError(f"Document version not found: {run.document_version_id}")

        if document_version.document_id != document.document_id:
            raise RuntimeError("Document version does not belong to the ingestion run document.")

        return document, document_version

    def _complete_run(self, run: IngestionRun) -> None:
        checkpoint = dict(run.checkpoint_data or {})
        if not checkpoint.get("archive_completed"):
            trigger_service = KnowledgeProcessingTriggerService(
                db=self.db,
            )

            trigger_service.trigger(
                document_version_id=run.document_version_id,
            )

        update_ingestion_stage(
            db=self.db,
            ingestion_run_id=run.ingestion_run_id,
            stage=IngestionStage.COMPLETED,
        )

        update_ingestion_status(
            db=self.db,
            ingestion_run_id=run.ingestion_run_id,
            run_status=IngestionRunStatus.COMPLETED,
        )

        self.db.commit()

    def _handle_failure(self, ingestion_run_id: str, exception: Exception) -> IngestionRun:
        run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

        failure = classify_failure(
            stage=run.current_stage,
            error_code=self._get_error_code(exception),
            message=str(exception),
            details={
                "exception_type": type(exception).__name__,
            },
        )

        record_ingestion_failure(
            db=self.db,
            ingestion_run_id=ingestion_run_id,
            failed_stage=failure.stage,
            error_code=failure.error_code,
            error_message=failure.message,
            error_details=failure.details,
        )

        self.db.commit()
        run = get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

        # A file that fails a security/format check fails it every time:
        # never retry it, and mark the document so users can see why.
        rejected = _is_security_rejection(exception)
        if rejected or failure.category == FailureCategory.PERMANENT:
            self._set_document_status(
                run, DocumentStatus.REJECTED if rejected else DocumentStatus.FAILED,
            )
            return run

        if run.retry_count >= run.max_retries:
            mark_retry_exhausted(db=self.db, ingestion_run_id=ingestion_run_id)
            self._set_document_status(run, DocumentStatus.FAILED)
            return get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

        schedule_retry(db=self.db, ingestion_run_id=ingestion_run_id)
        self.db.commit()

        return get_ingestion_run(db=self.db, ingestion_run_id=ingestion_run_id)

    def _set_document_status(self, run: IngestionRun, document_status: DocumentStatus) -> None:
        document = self.db.query(Document).filter(Document.document_id == run.document_id).first()
        if document is not None:
            document.status = document_status
            document.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()

    @staticmethod
    def _get_error_code(exception: Exception) -> str:
        error_code = getattr(exception, "error_code", None) or getattr(exception, "code", None)
        if error_code:
            return str(error_code)

        message = str(exception).strip()
        if message:
            candidate = message.split(":", 1)[0].strip()
            # The parser produced unusable output (e.g. a PDF with no text
            # layer). Parsing the same file again gives the same result.
            if candidate == "OutputValidationError":
                return "PARSER_VALIDATION_FAILED"
            if candidate in {
                "SECURITY_REJECTED",
                "SECURITY_REVIEW_REQUIRED",
                "MALICIOUS_ARTIFACT",
                "INVALID_ARTIFACT",
                "UNSUPPORTED_FORMAT",
                "FORMAT_VALIDATION_FAILED",
                "PARSER_NOT_FOUND",
                "PARSER_VALIDATION_FAILED",
                "ARTIFACT_NOT_FOUND",
                "INVALID_CONFIGURATION",
            }:
                return candidate
            if candidate in {
                "STORAGE_TEMPORARY_ERROR",
                "STORAGE_TIMEOUT",
                "STORAGE_UNAVAILABLE",
                "PARSER_TIMEOUT",
                "PARSER_PROCESS_CRASH",
                "PARSER_TEMPORARY_ERROR",
                "DATABASE_TEMPORARY_ERROR",
                "DATABASE_CONNECTION_ERROR",
                "NETWORK_TIMEOUT",
                "NETWORK_ERROR",
                "SERVICE_UNAVAILABLE",
            }:
                return candidate
        return "INGESTION_UNEXPECTED_ERROR"

_REJECTION_PREFIXES = ("SECURITY_REJECTED", "SECURITY_REVIEW_REQUIRED", "MALICIOUS_ARTIFACT")


def _is_security_rejection(exception: Exception) -> bool:
    """True when the file itself failed a security/format check.

    Scanner, storage and archive-extraction outages are not rejections:
    those stay retryable.
    """
    from app.knowledge.security.stage_1.exceptions import (
        HashGenerationError,
        MalwareScanError,
        StageOnePipelineError,
        StageOneValidationError,
        StorageVerificationError,
    )
    from app.knowledge.security.stage_2.exceptions import (
        ArchiveValidationError,
    )
    from app.knowledge.security.stage_3.exceptions import (
        StageThreeValidationError,
    )

    if isinstance(exception, (MalwareScanError, StorageVerificationError, HashGenerationError, StageOnePipelineError)):
        return False
    if isinstance(exception, (StageOneValidationError, ArchiveValidationError, StageThreeValidationError)):
        return True
    return str(exception).startswith(_REJECTION_PREFIXES)
