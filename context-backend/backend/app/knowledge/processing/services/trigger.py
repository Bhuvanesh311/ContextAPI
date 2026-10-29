from sqlalchemy.orm import Session

from app.core.enums import KnowledgeProcessingRunStatus
from app.infra.celery.app import celery_app
from app.knowledge.processing.services.lifecycle import (
    KnowledgeProcessingLifecycleService,
)
from app.knowledge.processing.tasks.processing import (
    run_knowledge_processing_task,
)
from app.knowledge.uploads.models import KnowledgeProcessingRun


class KnowledgeProcessingTriggerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.lifecycle = KnowledgeProcessingLifecycleService(db)

    def trigger(
        self,
        *,
        document_version_id: str,
    ) -> str:
        existing_run = self._get_existing_run(
            document_version_id=document_version_id,
        )

        if existing_run is not None:
            if existing_run.status in {
                KnowledgeProcessingRunStatus.PENDING,
                KnowledgeProcessingRunStatus.RUNNING,
                KnowledgeProcessingRunStatus.RETRYING,
            }:
                return existing_run.knowledge_processing_run_id

            if existing_run.status == KnowledgeProcessingRunStatus.COMPLETED:
                return existing_run.knowledge_processing_run_id

        run = self.lifecycle.create_run(
            document_version_id=document_version_id,
        )

        self.db.commit()

        run_knowledge_processing_task.delay(
            run.knowledge_processing_run_id,
        )

        return run.knowledge_processing_run_id

    def _get_existing_run(
        self,
        *,
        document_version_id: str,
    ) -> KnowledgeProcessingRun | None:
        return (
            self.db.query(KnowledgeProcessingRun)
            .filter(
                KnowledgeProcessingRun.document_version_id
                == document_version_id,
            )
            .order_by(
                KnowledgeProcessingRun.created_at.desc(),
            )
            .first()
        )