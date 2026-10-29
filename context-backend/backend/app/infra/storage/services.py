from dataclasses import dataclass
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.infra.storage.exceptions import (
    ObjectDeleteError,
    ObjectDownloadError,
    ObjectNotFoundError,
    ObjectStorageError,
    ObjectUploadError,
    BucketNotFoundError,
)


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    size: int
    etag: str | None = None


class ObjectStorageService:

    def __init__(self, client: Minio):
        self.client = client

    def upload(
        self,
        *,
        bucket: str,
        object_key: str,
        data: BinaryIO,
        size: int,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:

        try:
            result = self.client.put_object(
                bucket_name=bucket,
                object_name=object_key,
                data=data,
                length=size,
                content_type=content_type,
            )

            return StoredObject(
                bucket=bucket,
                object_key=object_key,
                size=size,
                etag=result.etag,
            )

        except S3Error as exc:
            raise ObjectUploadError(
                f"Failed to upload object '{object_key}'"
            ) from exc

    def exists(
        self,
        *,
        bucket: str,
        object_key: str,
    ) -> bool:

        try:
            self.client.stat_object(
                bucket_name=bucket,
                object_name=object_key,
            )

            return True

        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                return False

            if exc.code == "NoSuchBucket":
                raise BucketNotFoundError(
                    f"Bucket '{bucket}' does not exist"
                ) from exc

            raise ObjectStorageError(
                f"Failed to check object '{object_key}'"
            ) from exc

           

    def download(
        self,
        *,
        bucket: str,
        object_key: str,
    ):


        try:
            return self.client.get_object(
                bucket_name=bucket,
                object_name=object_key,
            )

        except S3Error as exc:
            if exc.code in {
                "NoSuchKey",
                "NoSuchObject",
            }:
                raise ObjectNotFoundError(
                    f"Object '{object_key}' does not exist"
                ) from exc

            raise ObjectDownloadError(
                f"Failed to download object '{object_key}'"
            ) from exc

    def delete(
        self,
        *,
        bucket: str,
        object_key: str,
    ) -> None:

        try:
            self.client.remove_object(
                bucket_name=bucket,
                object_name=object_key,
            )

        except S3Error as exc:
            raise ObjectDeleteError(
                f"Failed to delete object '{object_key}'"
            ) from exc