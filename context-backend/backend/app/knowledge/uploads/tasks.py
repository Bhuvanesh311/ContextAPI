from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.core.enums import IngestionRunStatus

from app.infra.celery.app import celery_app
from app.knowledge.cancellation import remember_task

from app.knowledge.uploads.ingestion_orchestrator import (
    IngestionOrchestrator,
)

logger = logging.getLogger(__name__)


@celery_app.task(
    name="knowledge.run_ingestion",
    bind=True,
)
def run_ingestion_task(
    self,
    ingestion_run_id: str,
) -> None:

    # Lets a stop request find (and kill) the process working on this run.
    remember_task(ingestion_run_id, self.request.id)

    db = SessionLocal()

    try:

        logger.info(
            "Ingestion task started",
            extra={
                "ingestion_run_id": ingestion_run_id,
            },
        )

        orchestrator = IngestionOrchestrator(
            db=db,
        )

        ingestion_run = orchestrator.run(
            ingestion_run_id=ingestion_run_id,
        )

        if (
            ingestion_run.status
            == IngestionRunStatus.RETRYING
        ):

            logger.info(
                "Ingestion run scheduled for retry",
                extra={
                    "ingestion_run_id": ingestion_run_id,
                    "next_retry_at": (
                        ingestion_run.next_retry_at
                    ),
                    "retry_count": (
                        ingestion_run.retry_count
                    ),
                },
            )

            # Nothing else picks RETRYING runs up: queue the retry here.
            delay_seconds = 0
            if ingestion_run.next_retry_at is not None:
                delay_seconds = max(
                    0,
                    int(
                        (
                            ingestion_run.next_retry_at
                            - datetime.now(timezone.utc).replace(tzinfo=None)
                        ).total_seconds()
                    ),
                )
            run_ingestion_task.apply_async(
                kwargs={"ingestion_run_id": ingestion_run_id},
                countdown=delay_seconds,
            )

            return

        if (
            ingestion_run.status
            == IngestionRunStatus.FAILED
        ):

            logger.error(
                "Ingestion run failed permanently",
                extra={
                    "ingestion_run_id": ingestion_run_id,
                    "failed_stage": (
                        ingestion_run.failed_stage
                    ),
                    "error_code": (
                        ingestion_run.error_code
                    ),
                    "error_message": (
                        ingestion_run.error_message
                    ),
                },
            )

            return

        if (
            ingestion_run.status
            == IngestionRunStatus.COMPLETED
        ):

            logger.info(
                "Ingestion run completed successfully",
                extra={
                    "ingestion_run_id": ingestion_run_id,
                },
            )

            return

        logger.info(
            "Ingestion task finished",
            extra={
                "ingestion_run_id": ingestion_run_id,
                "status": ingestion_run.status,
                "current_stage": (
                    ingestion_run.current_stage
                ),
            },
        )

    except Exception:

        db.rollback()

        logger.exception(
            "Ingestion Celery task crashed",
            extra={
                "ingestion_run_id": ingestion_run_id,
            },
        )

        raise

    finally:

        db.close()

@celery_app.task(
    name="knowledge.cleanup_sandboxes",
)
def cleanup_sandboxes_task() -> None:
    """
    Remove parser sandboxes whose worker process is gone: queued after a
    stop request kills an ingestion task in the middle of parsing.
    """

    from app.knowledge.parsing.sandbox.pool import remove_orphan_sandboxes

    remove_orphan_sandboxes()
