class Neo4jError(Exception):
    """Base exception for Neo4j."""


class Neo4jConnectionError(Neo4jError):
    """Raised when Neo4j cannot be reached."""


class Neo4jUnavailableError(Neo4jError):
    """Raised when Neo4j is unavailable."""


class Neo4jQueryError(Neo4jError):
    """Raised when a Cypher query fails."""


class Neo4jTransactionError(Neo4jError):
    """Raised when a Neo4j transaction fails."""