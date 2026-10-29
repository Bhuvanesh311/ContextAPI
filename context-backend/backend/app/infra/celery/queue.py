from kombu import Queue

EMAIL_QUEUE     = Queue("email")
RETRIEVAL_QUEUE = Queue("retrieval")