from celery import Celery

from app.core.config import settings
import app.core.models

celery_app = Celery(
    "contextapi",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    # Prefork children of the retrieval worker load ~GBs of models in
    # worker_process_init; the 4 s default would kill them mid-load.
    worker_proc_alive_timeout=300,
)
celery_app.conf.beat_schedule = {
    "fail-stale-retrieval-requests": {
        "task": "app.retrieval.tasks.fail_stale_requests_task",
        "schedule": 300.0,
    },
    # Re-queue ingestion/processing runs left behind by a dead worker.
    "recover-stuck-knowledge-runs": {
        "task": "knowledge.recover_stuck_runs",
        "schedule": 300.0,
    },
}

celery_app.conf.imports = (
    "app.infra.celery.email_tasks",
    "app.knowledge.uploads.tasks",
    "app.knowledge.processing.tasks.processing",
    "app.knowledge.recovery",
    "app.retrieval.tasks",
)
# task_routes live in routing.py; import it here so every process that loads
# the Celery app (API, workers, beat) actually uses them.
from app.infra.celery import routing as _routing  # noqa: E402,F401
