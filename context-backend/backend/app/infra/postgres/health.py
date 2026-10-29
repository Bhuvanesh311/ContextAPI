from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.infra.postgres.client import engine
from app.infra.postgres.exceptions import (
    DatabaseConnectionError,
)


def check_postgres_health() -> bool:
    """
    Verify that PostgreSQL is reachable.
    """

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return True

    except SQLAlchemyError as exc:
        raise DatabaseConnectionError(
            "Unable to connect to the PostgreSQL server."
        ) from exc

    except Exception as exc:
        raise DatabaseConnectionError(
            "Unexpected error while connecting to PostgreSQL."
        ) from exc