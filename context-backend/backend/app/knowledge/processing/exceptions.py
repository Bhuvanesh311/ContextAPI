class KnowledgeProcessingError(Exception):
    """Base exception for knowledge processing failures."""


class KnowledgeProcessingStateError(KnowledgeProcessingError):
    """Raised when a knowledge processing run has an invalid state transition."""


class KnowledgeProcessingStageError(KnowledgeProcessingError):
    """Raised when a knowledge processing stage cannot be executed."""


class KnowledgeProcessingValidationError(KnowledgeProcessingError):
    """Raised when knowledge processing input or output fails validation."""


class KnowledgeProcessingRetryableError(KnowledgeProcessingError):
    """Raised when a knowledge processing failure is eligible for retry."""


class KnowledgeProcessingPermanentError(KnowledgeProcessingError):
    """Raised when a knowledge processing failure must not be retried."""