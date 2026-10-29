from app.infra.celery.app import celery_app
from app.infra.celery.queue import EMAIL_QUEUE, RETRIEVAL_QUEUE


celery_app.conf.task_routes = {
    "app.infra.celery.email_tasks.*": {
        "queue": EMAIL_QUEUE.name,
    },
    # Housekeeping runs on the default worker so a busy retrieval worker can't delay it.
    "app.retrieval.tasks.fail_stale_requests_task": {
        "queue": "celery",
    },
    "app.retrieval.tasks.*": {
        "queue": RETRIEVAL_QUEUE.name,
    },
    # Chunking + embedding needs BGE-M3. The retrieval worker (threads pool)
    # already holds one copy; prefork children would each load their own
    # (~2.3 GB each) and exhaust memory.
    "knowledge.run_processing": {
        "queue": "processing",
    },
    "knowledge.recover_stuck_runs": {
        "queue": "celery",
    },
}