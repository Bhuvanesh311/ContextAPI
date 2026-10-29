from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import shutil
import threading
import shlex

import docker
from docker.errors import APIError, DockerException, NotFound
from docker.models.containers import Container

from app.knowledge.parsing.enums import SandboxState
from app.knowledge.parsing.exceptions import (
    SandboxExecutionError,
    SandboxInitializationError,
)
from app.knowledge.parsing.sandbox.health import SandboxHealth
from app.knowledge.parsing.sandbox.limits import (
    DEFAULT_SANDBOX_LIMITS,
    SandboxLimits,
)
from app.knowledge.parsing.sandbox.workspace import Workspace
from app.knowledge.parsing.schemas import (
    SandboxJob,
    SandboxResult,
)


logger = logging.getLogger(__name__)



# The root filesystem stays read-only; LibreOffice and tesseract need a
# writable /tmp (LibreOffice creates its IPC pipe there and ignores TMPDIR).
SANDBOX_TMPFS = {"/tmp": "rw,noexec,nosuid,size=512m,mode=1777"}

class SandboxWorker:
    """
    Persistent Docker-based sandbox worker.

    A worker owns exactly one sandbox container and reuses it
    across multiple parsing jobs.

    After every successful parsing job:
        1. Parser process finishes.
        2. Workspace is sanitized.
        3. Worker returns to READY.

    If the container becomes unsafe or unhealthy:
        1. Worker is marked FAILED.
        2. Container is destroyed.
        3. A replacement container can be created.
    """

    def __init__(
    self,
    workspace_root: Path,
    worker_id: str | None = None,
    image: str = "contextapi/parser-sandbox:latest",
    limits: SandboxLimits = DEFAULT_SANDBOX_LIMITS,
) -> None:
        self.worker_id = worker_id or str(uuid.uuid4())

        self.state = SandboxState.CREATING

        self.created_at = datetime.now(UTC)

        self.image = image

        self.limits = limits

        self.health = SandboxHealth(limits)

        self.workspace_root = Path(workspace_root)

        self.workspace = None

        self.client = docker.from_env()

        self.container = None

        logger.info(
            "Sandbox worker initialized",
            extra={
                "worker_id": self.worker_id,
                "workspace_root": str(self.workspace_root),
            },
        )

    def _is_container_compatible(self, container: Container) -> bool:
        """
        Check if an existing container satisfies the worker's security and limits.
        """
        try:
            attrs = container.attrs
            config = attrs.get("Config", {})
            host_config = attrs.get("HostConfig", {})

            if config.get("Image") != self.image:
                return False

            # Same tag but a rebuilt image: the container runs old parser code.
            try:
                if attrs.get("Image") != self.client.images.get(self.image).id:
                    return False
            except Exception:
                return False

            labels = config.get("Labels", {})
            if labels.get("com.contextapi.component") != "parser-sandbox":
                return False
            if labels.get("com.contextapi.worker-id") != self.worker_id:
                return False

            if bool(config.get("NetworkDisabled")) != (not self.limits.network_enabled):
                return False

            if host_config.get("ReadonlyRootfs") != self.limits.readonly_rootfs:
                return False

            if "/tmp" not in (host_config.get("Tmpfs") or {}):
                return False

            security_opt = host_config.get("SecurityOpt") or []
            if "no-new-privileges:true" not in security_opt:
                return False

            expected_mem = self.limits.memory_limit_mb * 1024 * 1024
            if host_config.get("Memory") != expected_mem:
                return False

            expected_cpus = int(self.limits.cpu_count * 1_000_000_000)
            if host_config.get("NanoCpus") != expected_cpus:
                return False

            if host_config.get("PidsLimit") != self.limits.max_processes:
                return False

            binds = host_config.get("Binds") or []
            expected_binds = {
                f"{str(self.workspace.input.resolve())}:/workspace/input:ro",
                f"{str(self.workspace.output.resolve())}:/workspace/output:rw",
                f"{str(self.workspace.temp.resolve())}:/workspace/temp:rw",
                f"{str(self.workspace.logs.resolve())}:/workspace/logs:rw",
            }
            
            # Use sets for order-independent comparison
            if set(binds) != expected_binds:
                return False

            return True

        except Exception as exc:
            logger.warning(
                "Error checking container compatibility",
                exc_info=exc,
            )
            return False

    def _create_container(self) -> Container:
        """
        Create the persistent Docker sandbox container safely and idempotently.
        """

        if self.container is not None:
            raise SandboxInitializationError(
                f"Worker {self.worker_id} already owns a container."
            )

        if self.workspace is None:
            raise SandboxInitializationError(
                f"Worker {self.worker_id} has no workspace configured."
            )

        try:
            self.workspace.create()

            container_name = f"contextapi-sandbox-{self.worker_id}"
            
            # 1. Check if it already exists
            try:
                existing = self.client.containers.get(container_name)
                
                if self._is_container_compatible(existing):
                    logger.info(
                        "Reusing compatible existing sandbox container",
                        extra={
                            "worker_id": self.worker_id,
                            "container_id": existing.id,
                            "container_name": container_name,
                        },
                    )
                    self.container = existing
                    return existing
                    
                logger.warning(
                    "Existing sandbox container is incompatible; destroying it",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": existing.id,
                        "container_name": container_name,
                    },
                )
                existing.remove(force=True)
            except NotFound:
                pass

            # 2. Create the container
            try:
                container = self.client.containers.create(
                    image=self.image,
                    name=container_name,
                    command=["sleep", "infinity"],
                    network_disabled=not self.limits.network_enabled,
                    read_only=self.limits.readonly_rootfs,
                    tmpfs=SANDBOX_TMPFS,
                    security_opt=[
                        "no-new-privileges:true",
                    ],
                    mem_limit=f"{self.limits.memory_limit_mb}m",
                    nano_cpus=int(
                        self.limits.cpu_count * 1_000_000_000
                    ),
                    pids_limit=self.limits.max_processes,
                    volumes={
                        str(self.workspace.input.resolve()): {
                            "bind": "/workspace/input",
                            "mode": "ro",
                        },
                        str(self.workspace.output.resolve()): {
                            "bind": "/workspace/output",
                            "mode": "rw",
                        },
                        str(self.workspace.temp.resolve()): {
                            "bind": "/workspace/temp",
                            "mode": "rw",
                        },
                        str(self.workspace.logs.resolve()): {
                            "bind": "/workspace/logs",
                            "mode": "rw",
                        },
                    },
                    labels={
                        "com.contextapi.component": "parser-sandbox",
                        "com.contextapi.worker-id": self.worker_id,
                    },
                )
            except APIError as exc:
                if exc.response is not None and exc.response.status_code == 409:
                    # Race condition: someone else created it right after our check
                    logger.warning(
                        "Encountered 409 Conflict during container creation; retrying acquisition",
                        extra={"worker_id": self.worker_id}
                    )
                    existing = self.client.containers.get(container_name)
                    if self._is_container_compatible(existing):
                        logger.info(
                            "Reusing compatible sandbox container after race",
                            extra={
                                "worker_id": self.worker_id,
                                "container_id": existing.id,
                                "container_name": container_name,
                            },
                        )
                        self.container = existing
                        return existing
                    else:
                        existing.remove(force=True)
                        container = self.client.containers.create(
                            image=self.image,
                            name=container_name,
                            command=["sleep", "infinity"],
                            network_disabled=not self.limits.network_enabled,
                            read_only=self.limits.readonly_rootfs,
                            tmpfs=SANDBOX_TMPFS,
                            security_opt=["no-new-privileges:true"],
                            mem_limit=f"{self.limits.memory_limit_mb}m",
                            nano_cpus=int(self.limits.cpu_count * 1_000_000_000),
                            pids_limit=self.limits.max_processes,
                            volumes={
                                str(self.workspace.input.resolve()): {"bind": "/workspace/input", "mode": "ro"},
                                str(self.workspace.output.resolve()): {"bind": "/workspace/output", "mode": "rw"},
                                str(self.workspace.temp.resolve()): {"bind": "/workspace/temp", "mode": "rw"},
                                str(self.workspace.logs.resolve()): {"bind": "/workspace/logs", "mode": "rw"},
                            },
                            labels={
                                "com.contextapi.component": "parser-sandbox",
                                "com.contextapi.worker-id": self.worker_id,
                            },
                        )
                else:
                    raise

            self.container = container

            logger.info(
                "Sandbox container created",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": container.id,
                    "container_name": container_name,
                },
            )

            return container

        except (DockerException, APIError) as exc:
            self.state = SandboxState.FAILED

            logger.exception(
                "Failed to create sandbox container",
                extra={
                    "worker_id": self.worker_id,
                },
            )

            raise SandboxInitializationError(
                f"Failed to create sandbox container "
                f"for worker {self.worker_id}"
            ) from exc

    def _start_container(self) -> None:
        """
        Start the worker's persistent sandbox container.

        The container must already have been created by
        _create_container().
        """

        if self.container is None:
            raise SandboxInitializationError(
                f"Worker {self.worker_id} has no container to start."
            )

        try:
            self.state = SandboxState.STARTING

            self.container.start()

            # Refresh container state from Docker after starting.
            self.container.reload()

            if self.container.status != "running":
                self.state = SandboxState.FAILED

                raise SandboxInitializationError(
                    f"Sandbox container failed to start. "
                    f"Current status: {self.container.status}"
                )

            self.state = SandboxState.READY

            # Reset health information when the container becomes ready.
            self.health.reset()

            logger.info(
                "Sandbox container started successfully",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": self.container.id,
                    "container_status": self.container.status,
                },
            )

        except (DockerException, APIError) as exc:
            self.state = SandboxState.FAILED

            logger.exception(
                "Failed to start sandbox container",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": self.container.id,
                },
            )

            raise SandboxInitializationError(
                f"Failed to start sandbox container "
                f"for worker {self.worker_id}."
            ) from exc

    def _stop_container(self) -> None:
        """
        Gracefully stop the worker's persistent sandbox container.

        This method stops the container but does not remove it.
        Destruction is handled separately by _destroy_container().
        """

        if self.container is None:
            logger.debug(
                "No container to stop",
                extra={
                    "worker_id": self.worker_id,
                },
            )
            return

        try:
            self.state = SandboxState.STOPPING

            self.container.reload()

            if self.container.status == "running":
                self.container.stop(
                    timeout=10,
                )

                logger.info(
                    "Sandbox container stopped",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": self.container.id,
                    },
                )

            self.state = SandboxState.STOPPED

        except NotFound:
            # The container has already been removed.
            self.container = None
            self.state = SandboxState.STOPPED

            logger.warning(
                "Sandbox container was already removed",
                extra={
                    "worker_id": self.worker_id,
                },
            )

        except (DockerException, APIError) as exc:
            self.state = SandboxState.FAILED

            logger.exception(
                "Failed to stop sandbox container",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": self.container.id,
                },
            )

            raise SandboxExecutionError(
                f"Failed to stop sandbox container "
                f"for worker {self.worker_id}."
            ) from exc

    def _destroy_container(self) -> None:
        """
        Stop and completely remove the worker's sandbox container.

        This is used when:
            - The sandbox becomes unhealthy.
            - A parsing job compromises the container.
            - The worker must be recycled.
            - The worker is permanently shutting down.

        After successful destruction, self.container is set to None.
        """

        if self.container is None:
            logger.debug(
                "No container to destroy",
                extra={
                    "worker_id": self.worker_id,
                },
            )
            return

        container_id = self.container.id

        try:
            self.state = SandboxState.RECYCLING

            # Refresh the container state before attempting removal.
            try:
                self.container.reload()
            except NotFound:
                # Container has already disappeared.
                self.container = None
                self.state = SandboxState.DESTROYED

                logger.warning(
                    "Sandbox container was already removed",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": container_id,
                    },
                )

                return

            self.container.remove(
                force=True,
            )

            self.container = None

            self.state = SandboxState.DESTROYED

            logger.info(
                "Sandbox container destroyed",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": container_id,
                },
            )

        except NotFound:
            self.container = None
            self.state = SandboxState.DESTROYED

            logger.warning(
                "Sandbox container no longer exists",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": container_id,
                },
            )

        except (DockerException, APIError) as exc:
            self.state = SandboxState.FAILED

            logger.exception(
                "Failed to destroy sandbox container",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": container_id,
                },
            )

            raise SandboxExecutionError(
                f"Failed to destroy sandbox container "
                f"for worker {self.worker_id}."
            ) from exc

    def _execute(
        self,
        command: list[str],
        timeout: int,
        workdir: str | None = None,
    ) -> tuple[int, bytes, bytes]:

        if self.container is None:
            raise SandboxExecutionError(
                f"Worker {self.worker_id} has no container."
            )
        
        exec_id = self.client.api.exec_create(
            container=self.container.id,
            cmd=command,
            workdir=workdir,
            stdout=True,
            stderr=True,
        )

        if self.state not in (
            SandboxState.READY,
            SandboxState.BUSY,
        ):
            raise SandboxExecutionError(
                f"Worker {self.worker_id} cannot execute a command "
                f"in its current state. "
                f"Current state: {self.state.value}"
            )

        try:
            # Validate container

            self.container.reload()

            if self.container.status != "running":
                self.state = SandboxState.FAILED

                raise SandboxExecutionError(
                    f"Sandbox container is not running. "
                    f"Current status: {self.container.status}"
                )

            # Determine timeout

            execution_timeout = (
                timeout
                if timeout is not None
                else int(
                    self.limits.execution_timeout.total_seconds()
                )
            )

            if execution_timeout <= 0:
                raise SandboxExecutionError(
                    "Sandbox execution timeout must be greater than zero."
                )

            # Mark worker busy

            self.state = SandboxState.BUSY

            logger.info(
                "Executing sandbox command",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": self.container.id,
                    "command": command,
                    "timeout_seconds": execution_timeout,
                    "workdir": workdir,
                },
            )

            # Shared execution result

            result: dict[str, Any] = {
                "exit_code": None,
                "stdout": b"",
                "stderr": b"",
                "exception": None,
            }

            # Docker execution function

            def execute() -> None:
               

                try:
                    if self.container is None:
                        raise SandboxExecutionError(
                            "Sandbox container disappeared "
                            "during execution."
                        )

                    exec_result = self.container.exec_run(
                        cmd=command,
                        workdir=workdir,
                        stdout=True,
                        stderr=True,
                        demux=True,
                    )

                    result["exit_code"] = exec_result.exit_code

                    if exec_result.output is not None:
                        stdout, stderr = exec_result.output

                        result["stdout"] = stdout or b""
                        result["stderr"] = stderr or b""

                except Exception as exc:
                    result["exception"] = exc

            # Start Docker execution

            execution_thread = threading.Thread(
                target=execute,
                name=f"sandbox-exec-{self.worker_id}",
                daemon=True,
            )

            execution_thread.start()

            # Wait for execution

            execution_thread.join(
                timeout=execution_timeout,
            )

            # HARD TIMEOUT

            if execution_thread.is_alive():

                logger.error(
                    "Sandbox execution timed out",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": self.container.id,
                        "timeout_seconds": execution_timeout,
                        "command": command,
                    },
                )

                self.state = SandboxState.FAILED
                self.health.mark_failed()

                try:
                    self._destroy_container()

                except Exception:
                    logger.exception(
                        "Failed to destroy timed-out "
                        "sandbox container",
                        extra={
                            "worker_id": self.worker_id,
                        },
                    )

                raise SandboxExecutionError(
                    f"Sandbox job exceeded the execution timeout "
                    f"of {execution_timeout} seconds."
                )

            # Docker execution exception

            if result["exception"] is not None:

                self.state = SandboxState.FAILED
                self.health.mark_failed()

                exception = result["exception"]

                logger.error(
                    "Docker execution failed",
                    exc_info=exception,
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": (
                            self.container.id
                            if self.container is not None
                            else None
                        ),
                    },
                )

                raise SandboxExecutionError(
                    f"Failed to execute command in sandbox "
                    f"for worker {self.worker_id}."
                ) from exception

            # Retrieve result

            exit_code = result["exit_code"]
            stdout = result["stdout"]
            stderr = result["stderr"]

            if exit_code is None:
                self.state = SandboxState.FAILED
                self.health.mark_failed()

                raise SandboxExecutionError(
                    "Sandbox execution completed without "
                    "returning an exit code."
                )

            # Parser completed

            if exit_code != 0:

                logger.warning(
                    "Sandbox parser returned non-zero exit code",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": (
                            self.container.id
                            if self.container is not None
                            else None
                        ),
                        "exit_code": exit_code,
                        "stderr": stderr.decode(
                            "utf-8",
                            errors="replace",
                        )[-4000:],
                    },
                )

            else:

                logger.info(
                    "Sandbox command completed successfully",
                    extra={
                        "worker_id": self.worker_id,
                        "container_id": (
                            self.container.id
                            if self.container is not None
                            else None
                        ),
                        "exit_code": exit_code,
                    },
                )

            return exit_code, stdout, stderr

        # Sandbox execution errors

        except SandboxExecutionError:
            raise

        # Docker errors

        except (DockerException, APIError) as exc:

            self.state = SandboxState.FAILED
            self.health.mark_failed()

            logger.exception(
                "Docker operation failed during sandbox execution",
                extra={
                    "worker_id": self.worker_id,
                },
            )

            raise SandboxExecutionError(
                f"Docker execution failed for worker "
                f"{self.worker_id}."
            ) from exc

        # Unexpected errors

        except Exception as exc:

            self.state = SandboxState.FAILED
            self.health.mark_failed()

            logger.exception(
                "Unexpected sandbox execution failure",
                extra={
                    "worker_id": self.worker_id,
                },
            )

            raise SandboxExecutionError(
                f"Unexpected sandbox execution failure "
                f"for worker {self.worker_id}."
            ) from exc

    def _cleanup_workspace(self) -> None:
       
    
        if self.workspace is None:
            logger.warning(
                "No workspace configured for cleanup",
                extra={
                    "worker_id": self.worker_id,
                },
            )
            return
    
        try:
            logger.info(
                "Cleaning sandbox workspace",
                extra={
                    "worker_id": self.worker_id,
                    "workspace": str(self.workspace.root),
                },
            )
    
            self.workspace.cleanup()
    
            if not self.workspace.is_empty():
                raise SandboxExecutionError(
                    f"Workspace cleanup verification failed for "
                    f"worker {self.worker_id}."
                )
    
            logger.info(
                "Sandbox workspace sanitized successfully",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
        except SandboxExecutionError:
            self.state = SandboxState.FAILED
    
            logger.exception(
                "Sandbox workspace cleanup verification failed",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            raise
        
        except Exception as exc:
            self.state = SandboxState.FAILED
    
            logger.exception(
                "Failed to sanitize sandbox workspace",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            raise SandboxExecutionError(
                f"Failed to sanitize workspace for "
                f"worker {self.worker_id}."
            ) from exc

    def _validate_output_size(self) -> None:
       

        if self.workspace is None:
            raise SandboxExecutionError(
                f"Worker {self.worker_id} has no workspace."
            )

        max_output_bytes = (
            self.limits.max_output_size_mb
            * 1024
            * 1024
        )

        total_size = 0

        for path in self.workspace.output.rglob("*"):
            if not path.is_file():
                continue

            try:
                total_size += path.stat().st_size
            except OSError as exc:
                raise SandboxExecutionError(
                    f"Failed to inspect sandbox output "
                    f"for worker {self.worker_id}."
                ) from exc

            if total_size > max_output_bytes:
                logger.error(
                    "Sandbox output size limit exceeded",
                    extra={
                        "worker_id": self.worker_id,
                        "output_size_bytes": total_size,
                        "max_output_size_bytes": max_output_bytes,
                    },
                )

                self.state = SandboxState.FAILED
                self.health.mark_failed()

                raise SandboxExecutionError(
                    f"Sandbox output exceeded the configured "
                    f"limit of {self.limits.max_output_size_mb} MB."
                )  
            
    def _recreate(self) -> None:
      
        logger.warning(
            "Recreating sandbox worker container",
            extra={
                "worker_id": self.worker_id,
                "container_id": (
                    self.container.id
                    if self.container is not None
                    else None
                ),
            },
        )
    
        self.state = SandboxState.RECYCLING
    
        try:
                # 1. Destroy existing container
        
            self._destroy_container()
    
                # 2. Reset workspace
        
            if self.workspace is not None:
                self.workspace.destroy()
    
                self.workspace.create()
    
                # 3. Reset health
        
            self.health.reset()
    
                # 4. Create replacement container
        
            self.state = SandboxState.CREATING
    
            self._create_container()
    
                # 5. Start replacement container
        
            self._start_container()
    
            logger.info(
                "Sandbox worker successfully recreated",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": (
                        self.container.id
                        if self.container is not None
                        else None
                    ),
                },
            )
    
        except Exception as exc:
            self.state = SandboxState.FAILED
    
            logger.exception(
                "Failed to recreate sandbox worker",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            raise SandboxInitializationError(
                f"Failed to recreate sandbox worker "
                f"{self.worker_id}."
            ) from exc
    
    def is_ready(self) -> bool:
       
        if self.state is not SandboxState.READY:
            return False
    
        if self.container is None:
            return False
    
        if self.workspace is None:
            return False
    
        try:
            self.container.reload()
    
            if self.container.status != "running":
                logger.warning(
                    "Worker container is not running",
                    extra={
                        "worker_id": self.worker_id,
                        "container_status": self.container.status,
                    },
                )
                return False
    
            if not self.health.is_healthy():
                logger.warning(
                    "Worker health check failed",
                    extra={
                        "worker_id": self.worker_id,
                        "health": self.health.summary(),
                    },
                )
                return False
    
            if not self.workspace.exists():
                logger.warning(
                    "Worker workspace does not exist",
                    extra={
                        "worker_id": self.worker_id,
                        "workspace": str(self.workspace.root),
                    },
                )
                return False
    
            return True
    
        except NotFound:
            logger.warning(
                "Worker container no longer exists",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            return False
    
        except (DockerException, APIError):
            logger.exception(
                "Failed to check worker readiness",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            return False
     
    def initialize(self) -> None:
       
    
        if self.state is not SandboxState.CREATING:
            raise SandboxInitializationError(
                f"Worker {self.worker_id} cannot be initialized "
                f"from state {self.state.value}."
            )
    
        try:
            logger.info(
                "Initializing sandbox worker",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
                # 1. Create workspace
        
            self.workspace = Workspace(
                root=self.workspace_root / self.worker_id,
            )

            self.workspace.create()
    
                # 2. Create persistent container
        
            self._create_container()
    
                # 3. Start container
        
            self._start_container()
    
            logger.info(
                "Sandbox worker initialized successfully",
                extra={
                    "worker_id": self.worker_id,
                    "container_id": (
                        self.container.id
                        if self.container is not None
                        else None
                    ),
                    "state": self.state.value,
                },
            )
    
        except Exception as exc:
            self.state = SandboxState.FAILED
    
            logger.exception(
                "Failed to initialize sandbox worker",
                extra={
                    "worker_id": self.worker_id,
                },
            )
    
            # Do not leave partially initialized resources behind.
            try:
                self._destroy_container()
            except Exception:
                logger.exception(
                    "Failed to cleanup container after "
                    "initialization failure",
                    extra={
                        "worker_id": self.worker_id,
                    },
                )
    
            if self.workspace is not None:
                try:
                    self.workspace.destroy()
                except Exception:
                    logger.exception(
                        "Failed to cleanup workspace after "
                        "initialization failure",
                        extra={
                            "worker_id": self.worker_id,
                        },
                    )
    
            raise SandboxInitializationError(
                f"Failed to initialize sandbox worker "
                f"{self.worker_id}."
            ) from exc
    
    def execute_job(self, job: SandboxJob) -> SandboxResult:
        

        if self.container is None:
            raise SandboxExecutionError(
                f"Worker {self.worker_id} has no container."
            )

        if self.workspace is None:
            raise SandboxExecutionError(
                f"Worker {self.worker_id} has no workspace."
            )

        if self.state is not SandboxState.READY:
            raise SandboxExecutionError(
                f"Worker {self.worker_id} is not ready for execution. "
                f"Current state: {self.state.value}"
            )

        # Validate Docker container

        try:
            self.container.reload()

        except NotFound as exc:
            self.state = SandboxState.FAILED
            self.health.mark_failed()

            raise SandboxExecutionError(
                f"Sandbox container for worker "
                f"{self.worker_id} no longer exists."
            ) from exc

        except (DockerException, APIError) as exc:
            self.state = SandboxState.FAILED
            self.health.mark_failed()

            raise SandboxExecutionError(
                f"Failed to inspect sandbox container "
                f"for worker {self.worker_id}."
            ) from exc

        if self.container.status != "running":
            self.state = SandboxState.FAILED
            self.health.mark_failed()

            raise SandboxExecutionError(
                f"Sandbox container is not running. "
                f"Current status: {self.container.status}"
            )

        self.state = SandboxState.BUSY

        logger.info(
            "Starting sandbox parsing job",
            extra={
                "worker_id": self.worker_id,
                "job_id": job.job_id,
                "container_id": self.container.id,
                "input_file": str(job.input_file),
            },
        )

        execution_failed = False

        try:
            # 1. CLEAN OLD WORKSPACE DATA

            self.workspace.cleanup()

            if not self.workspace.is_empty():
                raise SandboxExecutionError(
                    f"Sandbox workspace for worker "
                    f"{self.worker_id} could not be sanitized "
                    f"before starting the job."
                )

            # 2. VALIDATE SOURCE FILE

            source_file = Path(job.input_file)

            if not source_file.exists():
                raise SandboxExecutionError(
                    f"Sandbox input file does not exist: "
                    f"{source_file}"
                )

            if not source_file.is_file():
                raise SandboxExecutionError(
                    f"Sandbox input path is not a regular file: "
                    f"{source_file}"
                )

            # 3. COPY SOURCE DOCUMENT INTO SANDBOX INPUT

            destination = (
                self.workspace.input
                / source_file.name
            )

            shutil.copy2(
                source_file,
                destination,
            )

            logger.info(
                "Source document copied into sandbox",
                extra={
                    "worker_id": self.worker_id,
                    "job_id": job.job_id,
                    "source": str(source_file),
                    "destination": str(destination),
                },
            )

            # 4. SERIALIZE EXISTING ParsingRequest

            request_json = job.request.model_dump_json()

            # 5. BUILD RUNNER COMMAND

            runner_command = [
                "python",
                "-m",
                "app.knowledge.parsing.engine.runner",
            ]

            # 6. EXECUTE PARSER

            command = [
                "env",
                "PYTHONPATH=/sandbox",
                f"PARSING_REQUEST_JSON={request_json}",
            ] + runner_command

            exit_code, stdout, stderr = self._execute(
                command=command,
                timeout=int(
                    self.limits.execution_timeout.total_seconds()
                ),
                workdir="/workspace",
            )

            # 7. VALIDATE OUTPUT SIZE

            self._validate_output_size()

            # 8. READ PARSER RESULT

            result_file = (
                self.workspace.output
                / "parser_result.json"
            )

            parser_output = b""

            if result_file.exists():

                if not result_file.is_file():
                    raise SandboxExecutionError(
                        "Parser result path is not a regular file."
                    )

                parser_output = result_file.read_bytes()

            # 9. BUILD SANDBOX RESULT

            success = (
                exit_code == 0
                and bool(parser_output)
            )

            execution_result = SandboxResult(
                job_id=job.job_id,
                success=success,
                exit_code=exit_code,
                output=parser_output,
                error=stderr,
            )

            if success:
                logger.info(
                    "Sandbox parsing job completed successfully",
                    extra={
                        "worker_id": self.worker_id,
                        "job_id": job.job_id,
                        "exit_code": exit_code,
                        "result_size": len(parser_output),
                    },
                )
            else:
                logger.warning(
                    "Sandbox parsing job failed",
                    extra={
                        "worker_id": self.worker_id,
                        "job_id": job.job_id,
                        "exit_code": exit_code,
                        "result_size": len(parser_output),
                        "stderr": stderr.decode(
                            "utf-8",
                            errors="replace",
                        )[-4000:],
                    },
                )

            self.health.record_job()

            return execution_result

        except SandboxExecutionError:
            execution_failed = True
            self.state = SandboxState.FAILED
            self.health.mark_failed()
            raise

        except Exception as exc:
            execution_failed = True
            self.state = SandboxState.FAILED
            self.health.mark_failed()

            logger.exception(
                "Unexpected sandbox worker failure",
                extra={
                    "worker_id": self.worker_id,
                    "job_id": job.job_id,
                },
            )

            raise SandboxExecutionError(
                f"Unexpected sandbox failure for worker "
                f"{self.worker_id}."
            ) from exc

        finally:
            # 10. ALWAYS SANITIZE WORKSPACE

            try:
                self.state = SandboxState.CLEANING

                self._cleanup_workspace()

            except Exception as cleanup_exc:

                self.state = SandboxState.FAILED
                self.health.mark_failed()

                logger.exception(
                    "Sandbox workspace sanitization failed",
                    extra={
                        "worker_id": self.worker_id,
                        "job_id": job.job_id,
                    },
                )

                try:
                    self._recreate()

                except Exception as recreate_exc:

                    self.state = SandboxState.FAILED

                    logger.exception(
                        "Sandbox recreation failed after "
                        "workspace sanitization failure",
                        extra={
                            "worker_id": self.worker_id,
                            "job_id": job.job_id,
                        },
                    )

                    raise SandboxExecutionError(
                        f"Sandbox worker {self.worker_id} could "
                        f"not be sanitized or recreated."
                    ) from recreate_exc

                raise SandboxExecutionError(
                    f"Sandbox worker {self.worker_id} required "
                    f"recreation because workspace sanitization "
                    f"failed."
                ) from cleanup_exc

            # 11. RECYCLE OR RETURN TO READY

            if self.health.needs_recycle():

                try:
                    self.state = SandboxState.RECYCLING

                    logger.info(
                        "Recycling sandbox worker",
                        extra={
                            "worker_id": self.worker_id,
                            "job_id": job.job_id,
                            "health": self.health.summary(),
                        },
                    )

                    self._recreate()

                except Exception as recycle_exc:

                    self.state = SandboxState.FAILED
                    self.health.mark_failed()

                    logger.exception(
                        "Sandbox worker recycling failed",
                        extra={
                            "worker_id": self.worker_id,
                            "job_id": job.job_id,
                        },
                    )

                    raise SandboxExecutionError(
                        f"Failed to recycle sandbox worker "
                        f"{self.worker_id}."
                    ) from recycle_exc

            else:

                self.state = SandboxState.READY

                logger.debug(
                    "Sandbox worker returned to READY state",
                    extra={
                        "worker_id": self.worker_id,
                        "job_id": job.job_id,
                    },
                )

    def shutdown(self) -> None:
       
        logger.info(
            "Shutting down sandbox worker",
        extra={
            "worker_id": self.worker_id,
            "container_id": (
                self.container.id
                if self.container is not None
                else None
            ),
        },
    )

        self.state = SandboxState.STOPPING

        shutdown_error: Exception | None = None

        # 1. Destroy container

        try:
            self._destroy_container()

        except Exception as exc:
            shutdown_error = exc

            logger.exception(
                "Failed to destroy sandbox container during shutdown",
                extra={
                    "worker_id": self.worker_id,
                },
            )

        # 2. Destroy workspace

        if self.workspace is not None:
            try:
                self.workspace.destroy()

            except Exception as exc:
                shutdown_error = shutdown_error or exc

                logger.exception(
                    "Failed to destroy sandbox workspace during shutdown",
                    extra={
                        "worker_id": self.worker_id,
                        "workspace": str(self.workspace.root),
                    },
                )

        # 3. Clear references

        self.container = None
        self.workspace = None

        # 4. Final state

        if shutdown_error is not None:
            self.state = SandboxState.FAILED

            raise SandboxExecutionError(
                f"Failed to completely shutdown "
                f"sandbox worker {self.worker_id}."
            ) from shutdown_error

        self.state = SandboxState.STOPPED

        logger.info(
            "Sandbox worker shutdown complete",
            extra={
                "worker_id": self.worker_id,
            },
        )
