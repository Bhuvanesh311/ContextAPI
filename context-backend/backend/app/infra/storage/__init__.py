from app.infra.storage.client import minio_client
from app.infra.storage.services import ObjectStorageService


storage_service = ObjectStorageService(minio_client)