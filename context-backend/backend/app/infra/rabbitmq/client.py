import pika

from app.infra.rabbitmq.config import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    RABBITMQ_USERNAME,
    RABBITMQ_PASSWORD,
    RABBITMQ_VHOST,
)

from app.infra.rabbitmq.constants import (
    DEFAULT_HEARTBEAT,
    DEFAULT_BLOCKED_CONNECTION_TIMEOUT,
    DEFAULT_CONNECTION_ATTEMPTS,
    DEFAULT_RETRY_DELAY,
)


credentials = pika.PlainCredentials(
    username=RABBITMQ_USERNAME,
    password=RABBITMQ_PASSWORD,
)


parameters = pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    virtual_host=RABBITMQ_VHOST,
    credentials=credentials,
    heartbeat=DEFAULT_HEARTBEAT,
    blocked_connection_timeout=DEFAULT_BLOCKED_CONNECTION_TIMEOUT,
    connection_attempts=DEFAULT_CONNECTION_ATTEMPTS,
    retry_delay=DEFAULT_RETRY_DELAY,
)


rabbitmq_connection = pika.BlockingConnection(parameters)

rabbitmq_channel = rabbitmq_connection.channel()