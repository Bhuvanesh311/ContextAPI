import logging
import threading

from celery.signals import worker_process_init, worker_ready

from app.infra.celery.app import celery_app
from app.infra.celery.queue import RETRIEVAL_QUEUE
from app.retrieval.bootstrap import register_capabilities

logger = logging.getLogger(__name__)

# The worker never imports router.py, so the L04 capability registry must be
# filled here too, or every plan fails with "No available capability".
register_capabilities()


def _consumes_retrieval_queue() -> bool:
    return RETRIEVAL_QUEUE.name in (celery_app.amqp.queues.consume_from or {})


@worker_process_init.connect
def _preload_in_pool_process(**_kwargs) -> None:
    # Prefork: each child is its own process and needs its own model copy.
    if _consumes_retrieval_queue():
        _preload_models()


@worker_ready.connect
def _preload_in_main_process(sender=None, **_kwargs) -> None:
    # solo / threads pools run tasks in the main process; prefork children
    # are handled by worker_process_init, so skip the parent there.
    from celery.concurrency.prefork import TaskPool as PreforkPool

    if isinstance(getattr(sender, "pool", None), PreforkPool):
        return
    if _consumes_retrieval_queue():
        _preload_models()


def _preload_models() -> None:
    # Load models before tasks run, so the first request isn't cut off by the
    # per-call timeouts while a model is still loading.
    from app.retrieval.engine.reranker import preload_reranker_model
    from app.retrieval.service import _get_semantic_operator

    preload_reranker_model()
    try:
        _get_semantic_operator().embedding_adapter.warm_up()
        logger.info("BGE-M3 embedding model loaded")
    except Exception:
        logger.warning("Could not preload BGE-M3 embedding model", exc_info=True)
    # Loading the LLM takes ~20 s on a CPU; do it now, in the background,
    # instead of during the first question.
    threading.Thread(target=_warm_up_llm, name="ollama-warm-up", daemon=True).start()


def _warm_up_llm() -> None:
    from app.infra.ollama.client import OllamaClient

    try:
        OllamaClient().warm_up()
        logger.info("Ollama model loaded")
    except Exception as exc:
        logger.warning("Could not preload the Ollama model: %s", exc)


@celery_app.task(name="app.retrieval.tasks.fail_stale_requests_task")
def fail_stale_requests_task() -> int:
    """Beat job: fail requests stuck in PENDING / RUNNING (see service.fail_stale_requests)."""
    from app.core.database import RetrievalSessionLocal
    from app.retrieval.service import fail_stale_requests

    db = RetrievalSessionLocal()
    try:
        count = fail_stale_requests(db)
        if count:
            logger.warning("Marked %d stale retrieval request(s) as FAILED", count)
        return count
    finally:
        db.close()


@celery_app.task(
    name="app.retrieval.tasks.run_retrieval_task",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def run_retrieval_task(self, request_id: str, canonical_dict: dict, top_k: int = 5) -> None:
    """Celery task: run the full L02-L11 pipeline for a retrieval request.

    Owns its own DB session so it's safe to run in a separate worker process.
    The HTTP handler persists the RetrievalRequest at PENDING, enqueues this
    task, then returns 202.  Clients poll GET /{request_id}/status.
    """
    from app.core.database import RetrievalSessionLocal
    from app.core.enums import RetrievalRequestStatus
    from app.retrieval.models import RetrievalRequest
    from app.retrieval.canonical.schemas import RetrievalContract
    from app.retrieval.service import commit_unless_cancelled, run_retrieval

    from datetime import datetime, timezone

    active = (RetrievalRequestStatus.PENDING, RetrievalRequestStatus.RUNNING)

    db = RetrievalSessionLocal()
    try:
        db_request = db.query(RetrievalRequest).filter_by(request_id=request_id).first()
        if db_request is None:
            logger.error("run_retrieval_task: request %s not found", request_id)
            return

        if db_request.status == RetrievalRequestStatus.CANCELLED:
            return

        canonical = RetrievalContract.model_validate(canonical_dict)
        run_retrieval(db, db_request, canonical, top_k=top_k)
        commit_unless_cancelled(db, db_request)
    except Exception:
        db.rollback()
        logger.exception("run_retrieval_task failed for request_id=%s", request_id)
        try:
            # Best-effort: mark FAILED so the client doesn't poll forever.
            db.query(RetrievalRequest).filter(
                RetrievalRequest.request_id == request_id,
                RetrievalRequest.status.in_(active),
            ).update(
                {
                    "status": RetrievalRequestStatus.FAILED,
                    "error_code": "TASK_ERROR",
                    "error_message": "Unexpected error in retrieval worker.",
                    "completed_at": datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
