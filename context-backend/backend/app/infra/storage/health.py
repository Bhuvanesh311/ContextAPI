from minio.error import S3Error

from app.infra.storage.client import minio_client
from app.infra.storage.exceptions import ObjectStorageError


def check_storage_health() -> bool:

    try:
        minio_client.list_buckets()
        return True

    except S3Error as exc:
        raise ObjectStorageError(
            "Unable to connect to the MinIO server."
        ) from exc

    except Exception as exc:
        raise ObjectStorageError(
            "Unexpected error while connecting to MinIO."
        ) from exc