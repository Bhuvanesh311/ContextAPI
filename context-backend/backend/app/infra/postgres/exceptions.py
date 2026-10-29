class PostgreSQLError(Exception):
    """Base exception for PostgreSQL."""


class DatabaseConnectionError(PostgreSQLError):
    """Raised when PostgreSQL cannot be reached."""


class DatabaseUnavailableError(PostgreSQLError):
    """Raised when PostgreSQL is unavailable."""


class TransactionError(PostgreSQLError):
    """Raised when a database transaction fails."""


class QueryExecutionError(PostgreSQLError):
    """Raised when a query execution fails."""