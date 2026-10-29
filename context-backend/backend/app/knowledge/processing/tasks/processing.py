from app.core.database import SessionLocal
from app.core.enums import KnowledgeProcessingRunStatus
from app.infra.celery.app import celery_app
from app.knowledge.cancellation import (
    CANCELLED_CODE,
    CANCELLED_MESSAGE,
    ProcessingCancelled,
    remember_task,
)
from app.knowledge.processing.dependencies import create_chunking_service
from app.knowledge.processing.orchestrator import (
    KnowledgeProcessingOrchestrator,
)
from app.knowledge.processing.services.lifecycle import (
    KnowledgeProcessingLifecycleService,
)
from app.knowledge.processing.stages.factory import (
    create_knowledge_processing_stage_registry,
)
from app.knowledge.uploads.models import KnowledgeProcessingRun


@celery_app.task(
    name="knowledge.run_processing",
    bind=True,
    max_retries=3,
    retry_backoff=True,
)
def run_knowledge_processing_task(
    self,
    knowledge_processing_run_id: str,
) -> None:
    remember_task(knowledge_processing_run_id, self.request.id)

    db = SessionLocal()

    try:
        lifecycle = KnowledgeProcessingLifecycleService(db)

        chunking_service = create_chunking_service()

        stage_registry = create_knowledge_processing_stage_registry(
            db=db,
            chunking_service=chunking_service,
        )

        orchestrator = KnowledgeProcessingOrchestrator(
            db=db,
            lifecycle=lifecycle,
            stage_registry=stage_registry,
        )

        orchestrator.run(
            knowledge_processing_run_id=knowledge_processing_run_id,
        )

        db.commit()

    except ProcessingCancelled:
        # Stopped by the user: record it (if the stop request has not yet)
        # and do not retry.
        db.rollback()
        run = db.get(KnowledgeProcessingRun, knowledge_processing_run_id)
        if run is not None and run.status != KnowledgeProcessingRunStatus.CANCELLED:
            run.status = KnowledgeProcessingRunStatus.CANCELLED
            run.error_code = CANCELLED_CODE
            run.error_message = CANCELLED_MESSAGE
            db.commit()

    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc)

    finally:
        db.close()