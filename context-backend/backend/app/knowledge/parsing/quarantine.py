from __future__ import annotations

import io
import logging
from pathlib import PurePosixPath

from app.infra.storage.client import minio_client
from app.infra.storage.exceptions import (
    ObjectNotFoundError,
    ObjectStorageError,
)
from app.infra.storage.services import ObjectStorageService
from app.knowledge.parsing.schemas import (
    ParsingRequest,
    ParserResult,
)

logger = logging.getLogger(__name__)

PARSED_JSON_CONTENT_TYPE = "application/json"


def build_parsed_object_key(
    source_object_key: str,
) -> str:
    """
    Build a fallback parsed-object key from the source object key.

    The preferred parsed_object_key comes from ParsingRequest.
    This fallback exists only for compatibility with callers that
    have not supplied one.
    """

    if not source_object_key:
        raise ObjectStorageError(
            "Source object key is empty."
        )

    path = PurePosixPath(source_object_key)

    if path.name in {"", ".", ".."}:
        raise ObjectStorageError(
            f"Invalid source object key: "
            f"'{source_object_key}'."
        )

    if path.suffix.lower() == ".json":
        return str(path)

    return str(
        path.with_suffix(".json")
    )


class QuarantineStorage:
    """
    Storage boundary for the parsing stage.

    Responsibilities:
    - Verify that the quarantined source exists.
    - Store normalized parser output in the dedicated parsed bucket.
    - Never overwrite or delete the quarantine source.
    """

    def __init__(
        self,
        storage: ObjectStorageService | None = None,
    ) -> None:
        self.storage = (
            storage
            if storage is not None
            else ObjectStorageService(
                minio_client
            )
        )

    # ------------------------------------------------------------------
    # QUARANTINE SOURCE
    # ------------------------------------------------------------------

    def verify_quarantine_object(
        self,
        *,
        request: ParsingRequest,
    ) -> None:
        """
        Verify that the original quarantined object still exists.

        The parsing stage must never modify this object.
        """

        bucket = request.quarantine_bucket
        object_key = request.source_object_key

        if not bucket:
            raise ObjectStorageError(
                "Quarantine bucket is empty."
            )

        if not object_key:
            raise ObjectStorageError(
                "Quarantine object key is empty."
            )

        exists = self.storage.exists(
            bucket=bucket,
            object_key=object_key,
        )

        if not exists:
            raise ObjectNotFoundError(
                f"Quarantine object '{object_key}' "
                f"does not exist in bucket "
                f"'{bucket}'."
            )

        logger.debug(
            "Quarantine source verified",
            extra={
                "document_id": request.document_id,
                "quarantine_bucket": bucket,
                "quarantine_object_key": object_key,
            },
        )

    # ------------------------------------------------------------------
    # PARSED ARTIFACT
    # ------------------------------------------------------------------

    def store_parsed_json(
        self,
        *,
        request: ParsingRequest,
        result: ParserResult,
    ) -> tuple[str, str]:
        """
        Store the normalized parser result in dedicated parsed storage.

        Important:
        - Reads/validates the quarantine source.
        - Writes ONLY to the parsed bucket.
        - Never overwrites the quarantine object.
        - Uses the parsed destination supplied by ParsingRequest.
        """

        # 1. Validate parser result.

        if not result.success:
            raise ObjectStorageError(
                "Cannot store parsed JSON because "
                "parsing was unsuccessful."
            )

        if result.document is None:
            raise ObjectStorageError(
                "Cannot store parsed JSON because "
                "the parser returned no normalized document."
            )

        # 2. Verify the original quarantine object.

        self.verify_quarantine_object(
            request=request,
        )

        # 3. Validate parsed destination.

        parsed_bucket = request.parsed_bucket

        if not parsed_bucket:
            raise ObjectStorageError(
                "Parsed bucket is empty."
            )

        parsed_object_key = request.parsed_object_key

        if not parsed_object_key:
            raise ObjectStorageError(
                "Parsed object key is empty."
            )

        # 4. Serialize normalized document.

        parsed_json = (
            result.document.model_dump_json(
                indent=2,
            )
        )

        parsed_bytes = parsed_json.encode(
            "utf-8",
        )

        parsed_stream = io.BytesIO(
            parsed_bytes,
        )

        # 5. Store ONLY in the parsed bucket.

        stored_object = self.storage.upload(
            bucket=parsed_bucket,
            object_key=parsed_object_key,
            data=parsed_stream,
            size=len(parsed_bytes),
            content_type=PARSED_JSON_CONTENT_TYPE,
        )

        logger.info(
            "Parsed JSON stored successfully",
            extra={
                "document_id": request.document_id,
                "quarantine_bucket": (
                    request.quarantine_bucket
                ),
                "quarantine_object_key": (
                    request.source_object_key
                ),
                "parsed_bucket": parsed_bucket,
                "parsed_object_key": parsed_object_key,
                "size": stored_object.size,
                "etag": stored_object.etag,
            },
        )

        return (
            parsed_bucket,
            parsed_object_key,
        )