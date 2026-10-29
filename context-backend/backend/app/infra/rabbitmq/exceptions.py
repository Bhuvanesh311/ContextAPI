class RabbitMQError(Exception):
    """Base exception for RabbitMQ."""


class RabbitMQConnectionError(RabbitMQError):
    """Raised when RabbitMQ cannot be reached."""


class RabbitMQUnavailableError(RabbitMQError):
    """Raised when RabbitMQ is unavailable."""


class RabbitMQChannelError(RabbitMQError):
    """Raised when a RabbitMQ channel cannot be created."""


class RabbitMQPublishError(RabbitMQError):
    """Raised when a message cannot be published."""


class RabbitMQConsumeError(RabbitMQError):
    """Raised when consuming messages fails."""