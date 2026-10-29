class ChromaDBError(Exception):
    """Base exception for ChromaDB."""


class ChromaConnectionError(ChromaDBError):
    """Raised when ChromaDB cannot be reached."""


class CollectionAlreadyExistsError(ChromaDBError):
    """Raised when creating an existing collection."""


class CollectionNotFoundError(ChromaDBError):
    """Raised when a collection cannot be found."""


class InvalidCollectionNameError(ChromaDBError):
    """Raised when a collection name is invalid."""


class InvalidEmbeddingError(ChromaDBError):
    """Raised when embeddings are invalid."""


class InvalidMetadataError(ChromaDBError):
    """Raised when metadata is invalid."""


class ChromaOperationError(ChromaDBError):
    """Raised when a ChromaDB operation fails."""