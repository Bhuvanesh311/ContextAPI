class ObjectStorageError(Exception):
    """Base exception for all object-storage failures."""
    pass


class ObjectNotFoundError(ObjectStorageError):
    """Raised when an object does not exist in storage."""
    pass


class BucketNotFoundError(ObjectStorageError):
    """Raised when the requested bucket does not exist."""
    pass


class ObjectUploadError(ObjectStorageError):
    """Raised when uploading an object fails."""
    pass


class ObjectDownloadError(ObjectStorageError):
    """Raised when downloading an object fails."""
    pass


class ObjectDeleteError(ObjectStorageError):
    """Raised when deleting an object fails."""
    pass