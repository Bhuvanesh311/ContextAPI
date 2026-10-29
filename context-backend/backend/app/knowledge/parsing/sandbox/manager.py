from __future__ import annotations

import logging

from app.knowledge.parsing.sandbox.limits import SandboxLimits
from app.knowledge.parsing.sandbox.pool import SandboxPool
from app.knowledge.parsing.sandbox.worker import SandboxWorker


logger = logging.getLogger(__name__)


class SandboxManager:


    def __init__(
        self,
        *,
        pool_size: int,
        image: str,
        workspace_root,
        limits: SandboxLimits,
    ) -> None:

        self.pool = SandboxPool(
            size=pool_size,
            image=image,
            workspace_root=workspace_root,
            limits=limits,
        )

        self._initialized = False
        self._shutdown = False

    # INITIALIZE

    def initialize(self) -> None:
 

        if self._initialized:
            return

        if self._shutdown:
            raise RuntimeError(
                "Cannot initialize a shutdown sandbox manager."
            )

        logger.info(
            "Initializing sandbox manager",
        )

        self.pool.initialize()

        self._initialized = True

        logger.info(
            "Sandbox manager initialized successfully",
        )

    # ACQUIRE

    def acquire(self) -> SandboxWorker:
   

        if not self._initialized:
            raise RuntimeError(
                "Sandbox manager has not been initialized."
            )

        if self._shutdown:
            raise RuntimeError(
                "Sandbox manager has been shut down."
            )

        return self.pool.acquire()

    # RELEASE

    def release(
        self,
        worker: SandboxWorker,
    ) -> None:
  

        if self._shutdown:
            logger.debug(
                "Ignoring worker release after shutdown",
                extra={
                    "worker_id": worker.worker_id,
                },
            )
            return

        self.pool.release(worker)

    # REPLACE

    def replace(
        self,
        worker: SandboxWorker,
    ) -> SandboxWorker:

        if not self._initialized:
            raise RuntimeError(
                "Sandbox manager has not been initialized."
            )

        if self._shutdown:
            raise RuntimeError(
                "Cannot replace worker after shutdown."
            )

        return self.pool.replace(worker)

    # SHUTDOWN

    def shutdown(self) -> None:


        if self._shutdown:
            return

        logger.info(
            "Shutting down sandbox manager",
        )

        self._shutdown = True

        try:
            self.pool.shutdown()

        finally:
            self._initialized = False

        logger.info(
            "Sandbox manager shutdown complete",
        )
