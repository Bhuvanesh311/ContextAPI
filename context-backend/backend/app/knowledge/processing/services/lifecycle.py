from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.enums import (
    KnowledgeProcessingRunStatus,
    KnowledgeProcessingStage,
)
from app.knowledge.processing.exceptions import (
    KnowledgeProcessingStateError,
)
from app.knowledge.processing.state import (
    get_next_stage,
    is_terminal_stage,
)
from app.knowledge.uploads.models import KnowledgeProcessingRun


class KnowledgeProcessingLifecycleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_run(
        self,
        knowledge_processing_run_id: str,
    ) -> KnowledgeProcessingRun:
        run = (
            self.db.query(KnowledgeProcessingRun)
            .filter(
                KnowledgeProcessingRun.knowledge_processing_run_id
                == knowledge_processing_run_id
            )
            .first()
        )

        if run is None:
            raise KnowledgeProcessingStateError(
                "Knowledge processing run not found: "
                f"{knowledge_processing_run_id}"
            )

        return run

    def create_run(
        self,
        *,
        document_version_id: str,
    ) -> KnowledgeProcessingRun:
        run = KnowledgeProcessingRun(
            knowledge_processing_run_id=self._generate_run_id(),
            document_version_id=document_version_id,
            status=KnowledgeProcessingRunStatus.PENDING,
            current_stage=KnowledgeProcessingStage.INITIALIZATION,
            attempt_number=1,
            retry_count=0,
            max_retries=3,
            checkpoint_data={},
        )

        self.db.add(run)
        self.db.flush()

        return run

    def start_run(
        self,
        run: KnowledgeProcessingRun,
    ) -> KnowledgeProcessingRun:
        if run.status in {
            KnowledgeProcessingRunStatus.COMPLETED,
            KnowledgeProcessingRunStatus.CANCELLED,
        }:
            raise KnowledgeProcessingStateError(
                "Cannot start a terminal knowledge processing run"
            )

        if run.status not in {
            KnowledgeProcessingRunStatus.PENDING,
            KnowledgeProcessingRunStatus.RETRYING,
        }:
            raise KnowledgeProcessingStateError(
                "Knowledge processing run cannot be started from status "
                f"{run.status.value}"
            )

        run.status = KnowledgeProcessingRunStatus.RUNNING

        if run.started_at is None:
            run.started_at = self._utc_now()

        run.next_retry_at = None

        self.db.flush()

        return run

    def update_checkpoint(
        self,
        *,
        run: KnowledgeProcessingRun,
        checkpoint_data: dict[str, Any],
    ) -> KnowledgeProcessingRun:
        if run.status != KnowledgeProcessingRunStatus.RUNNING:
            raise KnowledgeProcessingStateError(
                "Only a running knowledge processing run can update "
                "its checkpoint"
            )

        run.checkpoint_data = dict(checkpoint_data)

        self.db.flush()

        return run

    def advance_stage(
        self,
        run: KnowledgeProcessingRun,
    ) -> KnowledgeProcessingRun:
        if run.status != KnowledgeProcessingRunStatus.RUNNING:
            raise KnowledgeProcessingStateError(
                "Only a running knowledge processing run can advance stages"
            )

        if is_terminal_stage(run.current_stage):
            raise KnowledgeProcessingStateError(
                "Cannot advance a terminal knowledge processing stage"
            )

        next_stage = get_next_stage(run.current_stage)

        if next_stage is None:
            raise KnowledgeProcessingStateError(
                "No next stage exists for "
                f"{run.current_stage.value}"
            )

        run.current_stage = next_stage

        self.db.flush()

        return run

    def complete_run(
        self,
        run: KnowledgeProcessingRun,
    ) -> KnowledgeProcessingRun:
        if run.status != KnowledgeProcessingRunStatus.RUNNING:
            raise KnowledgeProcessingStateError(
                "Only a running knowledge processing run can be completed"
            )

        if run.current_stage != KnowledgeProcessingStage.COMPLETED:
            raise KnowledgeProcessingStateError(
                "Knowledge processing run cannot be completed before "
                "reaching the COMPLETED stage"
            )

        run.status = KnowledgeProcessingRunStatus.COMPLETED
        run.completed_at = self._utc_now()
        run.next_retry_at = None

        self.db.flush()

        return run

    def mark_failed(
        self,
        *,
        run: KnowledgeProcessingRun,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
    ) -> KnowledgeProcessingRun:
        run.status = KnowledgeProcessingRunStatus.FAILED
        run.failed_stage = run.current_stage
        run.error_code = error_code
        run.error_message = error_message
        run.error_details = error_details
        run.next_retry_at = None

        self.db.flush()

        return run

    def mark_retrying(
        self,
        *,
        run: KnowledgeProcessingRun,
        error_code: str,
        error_message: str,
        error_details: dict[str, Any] | None = None,
        next_retry_at: datetime | None = None,
    ) -> KnowledgeProcessingRun:
        if run.status not in {
            KnowledgeProcessingRunStatus.RUNNING,
            KnowledgeProcessingRunStatus.RETRYING,
        }:
            raise KnowledgeProcessingStateError(
                "Knowledge processing run cannot enter retrying state "
                f"from status {run.status.value}"
            )

        if run.retry_count >= run.max_retries:
            raise KnowledgeProcessingStateError(
                "Knowledge processing retry limit has been exhausted"
            )

        run.retry_count += 1
        run.attempt_number += 1
        run.status = KnowledgeProcessingRunStatus.RETRYING
        run.failed_stage = run.current_stage
        run.error_code = error_code
        run.error_message = error_message
        run.error_details = error_details
        run.next_retry_at = next_retry_at

        self.db.flush()

        return run

    @staticmethod
    def _generate_run_id() -> str:
        return uuid4().hex[:20]

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)