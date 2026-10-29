from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from app.infra.storage import storage_service
from app.infra.storage.exceptions import (
    ObjectNotFoundError,
    ObjectStorageError,
)

from app.knowledge.parsing.quarantine import (
    QuarantineStorage,
)

from app.knowledge.parsing.schemas import (
    ParsingRequest,
    ParserResult,
    SandboxJob,
    SandboxResult,
)

from app.knowledge.parsing.sandbox.manager import (
    SandboxManager,
)


logger = logging.getLogger(__name__)


class ParsingOrchestrator:

    def __init__(
        self,
        sandbox_manager: SandboxManager,
        quarantine_storage: QuarantineStorage | None = None,
    ) -> None:

        self.sandbox_manager = sandbox_manager

        self.quarantine_storage = (
            quarantine_storage
            if quarantine_storage is not None
            else QuarantineStorage(
                storage=storage_service,
            )
        )

        logger.info(
            "Parsing orchestrator created",
        )

       # INITIALIZE
   
    def initialize(self) -> None:

        logger.info(
            "Initializing parsing orchestrator",
        )

        try:

            self.sandbox_manager.initialize()

        except Exception:

            logger.exception(
                "Failed to initialize parsing orchestrator",
            )

            raise

        logger.info(
            "Parsing orchestrator initialized successfully",
        )

       # PARSE
   
    def parse(
        self,
        request: ParsingRequest,
    ) -> ParserResult:

        logger.info(
            "Starting document parsing",
            extra={
                "document_id": request.document_id,
                "project_id": request.project_id,
                "upload_id": request.upload_id,
                "quarantine_bucket": (
                    request.quarantine_bucket
                ),
                "source_object_key": (
                    request.source_object_key
                ),
                "parsed_bucket": (
                    request.parsed_bucket
                ),
                "parsed_object_key": (
                    request.parsed_object_key
                ),
            },
        )

        worker = None
        worker_replaced = False

        try:

                      # 1. VERIFY QUARANTINE SOURCE
          
            self.quarantine_storage.verify_quarantine_object(
                request=request,
            )

                      # 2. DOWNLOAD ORIGINAL QUARANTINE OBJECT
          
            with tempfile.TemporaryDirectory(
                prefix=(
                    f"contextapi-parse-"
                    f"{request.document_id}-"
                ),
            ) as temp_dir:

                temp_root = Path(temp_dir)

                source_file = (
                    temp_root
                    / Path(
                        request.original_filename
                    ).name
                )

                self._download_source(
                    request=request,
                    destination=source_file,
                )

                             # 3. CREATE SANDBOX JOB
             
                job = SandboxJob(
                    job_id=request.document_id,
                    input_file=source_file,
                    parser_command=[
                        "python",
                        "-m",
                        "app.knowledge.parsing.engine.runner",
                    ],
                    request=request,
                )

                logger.info(
                    "Sandbox parsing job prepared",
                    extra={
                        "document_id": (
                            request.document_id
                        ),
                        "source_file": str(
                            source_file
                        ),
                    },
                )

                             # 4. ACQUIRE SANDBOX WORKER
             
                worker = (
                    self.sandbox_manager.acquire()
                )

                logger.info(
                    "Sandbox worker acquired",
                    extra={
                        "document_id": (
                            request.document_id
                        ),
                        "worker_id": (
                            worker.worker_id
                        ),
                    },
                )

                             # 5. EXECUTE INSIDE SANDBOX
             
                sandbox_result = (
                    worker.execute_job(
                        job,
                    )
                )

                logger.info(
                    "Sandbox execution completed",
                    extra={
                        "document_id": (
                            request.document_id
                        ),
                        "worker_id": (
                            worker.worker_id
                        ),
                        "success": (
                            sandbox_result.success
                        ),
                        "exit_code": (
                            sandbox_result.exit_code
                        ),
                    },
                )

                             # 6. CONVERT RESULT
             
                parser_result = (
                    self._parse_sandbox_result(
                        sandbox_result,
                    )
                )

                             # 7. PARSER FAILURE
             
                if not parser_result.success:

                    logger.warning(
                        "Document parsing failed; "
                        "quarantine source remains untouched",
                        extra={
                            "document_id": (
                                request.document_id
                            ),
                            "worker_id": (
                                worker.worker_id
                            ),
                            "parser": (
                                parser_result.parser_name
                            ),
                            "error": (
                                parser_result.error_message
                            ),
                        },
                    )

                    return parser_result

                             # 8. STORE PARSED JSON
             
                (
                    parsed_bucket,
                    parsed_object_key,
                ) = (
                    self.quarantine_storage
                    .store_parsed_json(
                        request=request,
                        result=parser_result,
                    )
                )

                logger.info(
                    "Parsed JSON stored successfully",
                    extra={
                        "document_id": (
                            request.document_id
                        ),
                        "quarantine_bucket": (
                            request.quarantine_bucket
                        ),
                        "quarantine_object_key": (
                            request.source_object_key
                        ),
                        "parsed_bucket": (
                            parsed_bucket
                        ),
                        "parsed_object_key": (
                            parsed_object_key
                        ),
                        "content_type": (
                            "application/json"
                        ),
                    },
                )

                             # 9. SUCCESS
             
                return parser_result

        except ObjectNotFoundError:

            logger.exception(
                "Original quarantine object was not found",
                extra={
                    "document_id": (
                        request.document_id
                    ),
                    "bucket": (
                        request.quarantine_bucket
                    ),
                    "object_key": (
                        request.source_object_key
                    ),
                },
            )

            raise

        except ObjectStorageError:

            logger.exception(
                "Quarantine/parsing storage operation failed",
                extra={
                    "document_id": (
                        request.document_id
                    ),
                    "quarantine_bucket": (
                        request.quarantine_bucket
                    ),
                    "source_object_key": (
                        request.source_object_key
                    ),
                    "parsed_bucket": (
                        request.parsed_bucket
                    ),
                    "parsed_object_key": (
                        request.parsed_object_key
                    ),
                },
            )

            raise

        except Exception:

            logger.exception(
                "Parsing orchestration failed",
                extra={
                    "document_id": (
                        request.document_id
                    ),
                    "worker_id": (
                        worker.worker_id
                        if worker is not None
                        else None
                    ),
                },
            )

                     # Replace unhealthy worker
         
            if worker is not None:

                try:

                    if not worker.is_ready():

                        self.sandbox_manager.replace(
                            worker,
                        )

                        worker_replaced = True

                except Exception:

                    logger.exception(
                        "Failed to replace unhealthy "
                        "sandbox worker",
                        extra={
                            "document_id": (
                                request.document_id
                            ),
                            "worker_id": (
                                worker.worker_id
                            ),
                        },
                    )

            raise

        finally:

                     # Release healthy worker
         
            if (
                worker is not None
                and not worker_replaced
            ):

                try:

                    self.sandbox_manager.release(
                        worker,
                    )

                except Exception:

                    logger.exception(
                        "Failed to release sandbox worker",
                        extra={
                            "document_id": (
                                request.document_id
                            ),
                            "worker_id": (
                                worker.worker_id
                            ),
                        },
                    )

       # DOWNLOAD SOURCE
   
    def _download_source(
        self,
        *,
        request: ParsingRequest,
        destination: Path,
    ) -> None:

        response = None

        try:

            response = storage_service.download(
                bucket=request.quarantine_bucket,
                object_key=request.source_object_key,
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with destination.open(
                "wb",
            ) as output_file:

                shutil.copyfileobj(
                    response,
                    output_file,
                )

        except ObjectStorageError:

            raise

        except Exception as exc:

            raise ObjectStorageError(
                "Failed to download source document "
                f"'{request.source_object_key}'."
            ) from exc

        finally:

            if response is not None:

                try:
                    response.close()

                except Exception:

                    logger.warning(
                        "Failed to close MinIO "
                        "download response",
                        extra={
                            "document_id": (
                                request.document_id
                            ),
                        },
                    )

                try:
                    response.release_conn()

                except Exception:

                    logger.warning(
                        "Failed to release MinIO connection",
                        extra={
                            "document_id": (
                                request.document_id
                            ),
                        },
                    )

       # PARSER RESULT
   
    @staticmethod
    def _parse_sandbox_result(
        sandbox_result: SandboxResult,
    ) -> ParserResult:

        if not sandbox_result.output:

            stderr = sandbox_result.error.decode(
                "utf-8",
                errors="replace",
            )

            return ParserResult(
                success=False,
                parser_name="unknown",
                document=None,
                error_message=(
                    stderr
                    if stderr
                    else (
                        "Sandbox returned no "
                        "parser result."
                    )
                ),
            )

        try:

            return ParserResult.model_validate_json(
                sandbox_result.output,
            )

        except Exception as exc:

            stderr = sandbox_result.error.decode(
                "utf-8",
                errors="replace",
            )

            logger.exception(
                "Sandbox returned invalid "
                "ParserResult JSON",
                extra={
                    "job_id": (
                        sandbox_result.job_id
                    ),
                    "exit_code": (
                        sandbox_result.exit_code
                    ),
                },
            )

            return ParserResult(
                success=False,
                parser_name="unknown",
                document=None,
                error_message=(
                    "Sandbox returned invalid parser "
                    f"result JSON: {exc}. "
                    f"stderr: {stderr[-4000:]}"
                ),
            )

       # SHUTDOWN
   
    def shutdown(self) -> None:

        logger.info(
            "Shutting down parsing orchestrator",
        )

        try:

            self.sandbox_manager.shutdown()

        except Exception:

            logger.exception(
                "Failed to shutdown parsing orchestrator",
            )

            raise

        logger.info(
            "Parsing orchestrator shutdown complete",
        )