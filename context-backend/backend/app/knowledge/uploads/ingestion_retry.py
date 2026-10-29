from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.knowledge.uploads.models import IngestionRun
from app.knowledge.uploads.ingestion_service import (
    get_ingestion_run,
)
from app.core.enums import IngestionRunStatus


DEFAULT_BASE_DELAY_SECONDS = 30
DEFAULT_MAX_DELAY_SECONDS = 3600


def calculate_retry_delay(
    retry_count: int,
    base_delay_seconds: int = DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: int = DEFAULT_MAX_DELAY_SECONDS,
) -> int:

    delay = base_delay_seconds * (2 ** retry_count)

    return min(
        delay,
        max_delay_seconds,
    )


def can_retry(
    run: IngestionRun,
) -> bool:

    return (
        run.retry_count < run.max_retries
        and run.status
        in {
            IngestionRunStatus.FAILED,
            IngestionRunStatus.RETRYING,
        }
    )


def schedule_retry(
    db: Session,
    ingestion_run_id: str,
) -> IngestionRun:

    run = get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    if not can_retry(run):
        return run

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    delay_seconds = calculate_retry_delay(
        retry_count=run.retry_count,
    )

    run.retry_count += 1
    run.attempt_number += 1
    run.status = IngestionRunStatus.RETRYING
    run.next_retry_at = (
        now + timedelta(seconds=delay_seconds)
    )
    run.updated_at = now

    db.flush()

    return run


def mark_retry_started(
    db: Session,
    ingestion_run_id: str,
) -> IngestionRun:

    run = get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    run.status = IngestionRunStatus.RUNNING
    run.next_retry_at = None
    run.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.flush()

    return run


def mark_retry_exhausted(
    db: Session,
    ingestion_run_id: str,
) -> IngestionRun:

    run = get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    run.status = IngestionRunStatus.FAILED
    run.next_retry_at = None
    run.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.flush()

    return run


def is_retry_due(
    run: IngestionRun,
) -> bool:

    if run.status != IngestionRunStatus.RETRYING:
        return False

    if run.next_retry_at is None:
        return True

    return datetime.now(timezone.utc).replace(tzinfo=None) >= run.next_retry_at