from __future__ import annotations

import logging
import threading

from app.knowledge.parsing.exceptions import (
    SandboxInitializationError,
    SandboxUnavailableError,
)
from app.knowledge.parsing.sandbox.limits import SandboxLimits
from app.knowledge.parsing.sandbox.worker import SandboxWorker

import os
import socket

_logger = logging.getLogger(__name__)


def _owner_prefix() -> str:
    """sandbox-<host>-<pid>: unique per worker process on a Docker host.
    Inside a container the hostname is the container's short id."""
    return f"sandbox-{socket.gethostname()}-{os.getpid()}"


def _owner_alive(worker_id: str, client) -> bool:
    parts = worker_id.split("-")
    if len(parts) < 4 or parts[0] != "sandbox":
        return False                      # legacy fixed names (sandbox-worker-N)
    host, pid = parts[1], parts[2]
    if host == socket.gethostname():
        try:
            os.kill(int(pid), 0)
        except (OSError, ValueError):
            return False
        # A killed process stays a zombie until its parent reaps it, and
        # still answers kill(0); it is not coming back.
        try:
            with open(f"/proc/{int(pid)}/status") as status:
                for line in status:
                    if line.startswith("State:"):
                        return "Z" not in line.split()[1]
        except OSError:
            pass
        return True
    # Another worker container: alive while that container runs.
    try:
        return client.containers.get(host).status == "running"
    except Exception:
        return False


def remove_orphan_sandboxes() -> None:
    """Remove parser sandboxes whose owning worker process is gone."""
    try:
        import docker

        client = docker.from_env()
        containers = client.containers.list(
            all=True, filters={"label": "com.contextapi.component=parser-sandbox"},
        )
    except Exception:
        _logger.warning("Could not list parser sandboxes for cleanup", exc_info=True)
        return

    for container in containers:
        worker_id = container.labels.get("com.contextapi.worker-id", "")
        if _owner_alive(worker_id, client):
            continue
        try:
            container.remove(force=True)
            _logger.info("Removed orphan parser sandbox %s", container.name)
        except Exception:
            _logger.warning("Could not remove parser sandbox %s", container.name, exc_info=True)


logger = logging.getLogger(__name__)


class SandboxPool:
 
    def __init__(
        self,
        *,
        size: int,
        image: str,
        workspace_root,
        limits: SandboxLimits,
    ) -> None:

        if size <= 0:
            raise ValueError(
                "Sandbox pool size must be greater than zero."
            )

        self.size = size
        self.image = image
        self.workspace_root = workspace_root
        self.limits = limits

        self._workers: list[SandboxWorker] = []
        self._busy_workers: set[str] = set()

        self._lock = threading.RLock()

        self._condition = threading.Condition(
            self._lock,
        )

        self._initialized = False
        self._shutdown = False

    # INITIALIZATION

    def initialize(self) -> None:
     
        with self._condition:

            if self._initialized:
                return

            if self._shutdown:
                raise SandboxInitializationError(
                    "Cannot initialize a shutdown sandbox pool."
                )

            logger.info(
                "Initializing sandbox pool",
                extra={
                    "pool_size": self.size,
                },
            )

            created_workers: list[SandboxWorker] = []

            try:

                # Every worker process has its own pool: names must not
                # collide between processes, and pools of processes that
                # are gone must not linger.
                remove_orphan_sandboxes()

                for index in range(self.size):

                    worker_id = (
                        f"{_owner_prefix()}-{index + 1}"
                    )

                    worker = SandboxWorker(
                        worker_id=worker_id,
                        image=self.image,
                        workspace_root=self.workspace_root,
                        limits=self.limits,
                    )

                    worker.initialize()

                    created_workers.append(worker)

            except Exception as exc:

                logger.exception(
                    "Failed to initialize sandbox pool",
                )

                for worker in created_workers:

                    try:
                        worker.shutdown()

                    except Exception:
                        logger.exception(
                            "Failed to shutdown partially "
                            "initialized sandbox worker",
                            extra={
                                "worker_id": worker.worker_id,
                            },
                        )

                raise SandboxInitializationError(
                    "Failed to initialize sandbox pool."
                ) from exc

            self._workers = created_workers
            self._busy_workers.clear()
            self._initialized = True
            self._shutdown = False

            self._condition.notify_all()

            logger.info(
                "Sandbox pool initialized",
                extra={
                    "pool_size": len(self._workers),
                },
            )

    # ACQUIRE

    def acquire(self) -> SandboxWorker:
   

        with self._condition:

            while True:

                # Pool state validation

                if not self._initialized:
                    raise SandboxUnavailableError(
                        "Sandbox pool has not been initialized."
                    )

                if self._shutdown:
                    raise SandboxUnavailableError(
                        "Sandbox pool has been shut down."
                    )

                # Find available healthy worker

                for worker in self._workers:

                    worker_id = worker.worker_id

                    if worker_id in self._busy_workers:
                        continue

                    if not worker.is_ready():
                        continue

                    self._busy_workers.add(
                        worker_id,
                    )

                    logger.debug(
                        "Sandbox worker acquired",
                        extra={
                            "worker_id": worker_id,
                            "busy_workers": len(
                                self._busy_workers
                            ),
                            "pool_size": len(
                                self._workers
                            ),
                        },
                    )

                    return worker

                # No worker currently available

                logger.debug(
                    "All healthy sandbox workers are busy; "
                    "waiting for an available worker",
                    extra={
                        "busy_workers": len(
                            self._busy_workers
                        ),
                        "pool_size": len(
                            self._workers
                        ),
                    },
                )

                self._condition.wait()

    # RELEASE

    def release(
        self,
        worker: SandboxWorker,
    ) -> None:

        with self._condition:

            worker_id = worker.worker_id

            if worker_id not in self._busy_workers:

                logger.warning(
                    "Attempted to release a worker that is "
                    "not marked busy",
                    extra={
                        "worker_id": worker_id,
                    },
                )

                return

            self._busy_workers.remove(
                worker_id,
            )

            if self._shutdown:

                self._condition.notify_all()

                return

            # Healthy worker

            if worker.is_ready():

                logger.debug(
                    "Sandbox worker released",
                    extra={
                        "worker_id": worker_id,
                        "busy_workers": len(
                            self._busy_workers
                        ),
                    },
                )

                self._condition.notify()

                return

            # Unhealthy worker

            logger.warning(
                "Released worker is unhealthy; "
                "replacing worker",
                extra={
                    "worker_id": worker_id,
                },
            )

            try:

                self._replace_locked(
                    worker,
                )

            except Exception:

                logger.exception(
                    "Failed to replace unhealthy "
                    "sandbox worker",
                    extra={
                        "worker_id": worker_id,
                    },
                )

                self._condition.notify_all()

                raise

            self._condition.notify()

    # REPLACE

    def replace(
        self,
        worker: SandboxWorker,
    ) -> SandboxWorker:

        with self._condition:

            replacement = self._replace_locked(
                worker,
            )

            self._condition.notify_all()

            return replacement

    def _replace_locked(
    self,
    worker: SandboxWorker,
) -> SandboxWorker:

    
        if self._shutdown:
            raise SandboxUnavailableError(
                "Cannot replace a worker after pool shutdown."
            )
    
        old_worker_id = worker.worker_id
    
        try:
            worker_index = self._workers.index(worker)
        except ValueError as exc:
            raise SandboxUnavailableError(
                f"Worker {old_worker_id} does not belong "
                f"to this sandbox pool."
            ) from exc
    
        logger.info(
            "Replacing sandbox worker",
            extra={
                "worker_id": old_worker_id,
            },
        )
    
 
        # 1. COMPLETELY DESTROY OLD WORKER FIRST
      
    
        try:
            worker.shutdown()
    
        except Exception as exc:
            logger.exception(
                "Failed to completely shutdown old sandbox "
                "worker before replacement",
                extra={
                    "worker_id": old_worker_id,
                },
            )
    
            raise SandboxInitializationError(
                f"Cannot replace sandbox worker "
                f"{old_worker_id} because the old worker "
                f"could not be completely shutdown."
            ) from exc
    
        # 2. CREATE REPLACEMENT
    
        replacement = SandboxWorker(
            worker_id=old_worker_id,
            image=self.image,
            workspace_root=self.workspace_root,
            limits=self.limits,
        )
    
        try:
            replacement.initialize()
    
            if not replacement.is_ready():
                logger.error(
                    "Replacement sandbox worker failed "
                    "readiness check",
                    extra={
                        "worker_id": replacement.worker_id,
                        "state": replacement.state.value,
                        "container_id": (
                            replacement.container.id
                            if replacement.container is not None
                            else None
                        ),
                        "workspace": (
                            str(replacement.workspace.root)
                            if replacement.workspace is not None
                            else None
                        ),
                        "health": replacement.health.summary(),
                    },
                )
    
                try:
                    replacement.shutdown()
                except Exception:
                    logger.exception(
                        "Failed to shutdown non-ready "
                        "replacement worker",
                        extra={
                            "worker_id": replacement.worker_id,
                        },
                    )
    
                raise SandboxInitializationError(
                    f"Replacement sandbox worker "
                    f"{old_worker_id} initialized but "
                    f"is not ready."
                )
    
        except Exception as exc:
        
            logger.exception(
                "Failed to initialize replacement "
                "sandbox worker",
                extra={
                    "worker_id": old_worker_id,
                },
            )
    
            try:
                replacement.shutdown()
            except Exception:
                logger.exception(
                    "Failed to shutdown failed "
                    "replacement worker",
                    extra={
                        "worker_id": old_worker_id,
                    },
                )
    
            raise SandboxInitializationError(
                f"Failed to replace sandbox worker "
                f"{old_worker_id}."
            ) from exc
    
        # 3. SWAP WORKER
    
        self._workers[worker_index] = replacement
    
        self._busy_workers.discard(
            old_worker_id,
        )
    
        logger.info(
            "Sandbox worker replaced successfully",
            extra={
                "worker_id": replacement.worker_id,
                "pool_size": len(self._workers),
            },
        )
    
        return replacement

    # SHUTDOWN

    def shutdown(self) -> None:


        with self._condition:

            if self._shutdown:
                return

            logger.info(
                "Shutting down sandbox pool",
                extra={
                    "pool_size": len(
                        self._workers
                    ),
                },
            )

            self._shutdown = True

            workers = list(
                self._workers
            )

            self._workers.clear()
            self._busy_workers.clear()
            self._initialized = False

        
            self._condition.notify_all()

            for worker in workers:

                try:

                    worker.shutdown()

                except Exception:

                    logger.exception(
                        "Failed to shutdown sandbox worker "
                        "during pool shutdown",
                        extra={
                            "worker_id": worker.worker_id,
                        },
                    )

            logger.info(
                "Sandbox pool shutdown complete",
            )
