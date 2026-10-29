import logging


LOG_FORMAT = (
    "%(asctime)s | "
    "%(levelname)-8s | "
    "%(name)s | "
    "%(message)s"
)


def configure_logging() -> None:
    """
    Configure application-wide runtime logging.

    Stage 1 structured metadata is attached to LogRecord objects
    through logger.py using the `extra` argument.
    """

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )

    logging.getLogger(
        "knowledge.security.stage_1"
    ).setLevel(logging.INFO)