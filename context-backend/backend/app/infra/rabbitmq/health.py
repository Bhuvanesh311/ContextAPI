import pika
from pika.exceptions import AMQPConnectionError, AMQPError

from app.infra.rabbitmq.client import rabbitmq_connection
from app.infra.rabbitmq.exceptions import (
    RabbitMQConnectionError,
)


def check_rabbitmq_health() -> bool:
    """
    Verify that RabbitMQ is reachable.
    """

    try:
        if rabbitmq_connection.is_open:
            return True

        raise RabbitMQConnectionError(
            "RabbitMQ connection is closed."
        )

    except AMQPConnectionError as exc:
        raise RabbitMQConnectionError(
            "Unable to connect to the RabbitMQ server."
        ) from exc

    except AMQPError as exc:
        raise RabbitMQConnectionError(
            "RabbitMQ communication failed."
        ) from exc

    except Exception as exc:
        raise RabbitMQConnectionError(
            "Unexpected error while connecting to RabbitMQ."
        ) from exc