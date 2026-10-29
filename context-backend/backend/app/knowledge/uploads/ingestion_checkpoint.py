from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.knowledge.uploads.models import IngestionRun
from app.knowledge.uploads.ingestion_service import (
    get_ingestion_run,
    save_ingestion_checkpoint,
)


def build_checkpoint(
    *,
    stage: str,
    data: dict | None = None,
) -> dict:
    return {
        "stage": stage,
        "data": data or {},
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }


def save_stage_checkpoint(
    db: Session,
    ingestion_run_id: str,
    stage: str,
    data: dict | None = None,
) -> IngestionRun:

    checkpoint = build_checkpoint(
        stage=stage,
        data=data,
    )

    return save_ingestion_checkpoint(
        db=db,
        ingestion_run_id=ingestion_run_id,
        checkpoint_data=checkpoint,
    )


def get_checkpoint(
    db: Session,
    ingestion_run_id: str,
) -> dict | None:

    run = get_ingestion_run(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    return run.checkpoint_data


def get_last_completed_stage(
    db: Session,
    ingestion_run_id: str,
) -> str | None:

    checkpoint = get_checkpoint(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    if not checkpoint:
        return None

    return checkpoint.get("stage")


def get_checkpoint_data(
    db: Session,
    ingestion_run_id: str,
) -> dict:

    checkpoint = get_checkpoint(
        db=db,
        ingestion_run_id=ingestion_run_id,
    )

    if not checkpoint:
        return {}

    return checkpoint.get("data", {})