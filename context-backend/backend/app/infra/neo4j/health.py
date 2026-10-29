from neo4j.exceptions import Neo4jError as DriverNeo4jError

from app.infra.neo4j.client import neo4j_driver
from app.infra.neo4j.exceptions import Neo4jConnectionError


def check_neo4j_health() -> bool:
    """
    Verify that the Neo4j server is reachable.
    """

    try:
        neo4j_driver.verify_connectivity()
        return True

    except DriverNeo4jError as exc:
        raise Neo4jConnectionError(
            "Unable to connect to the Neo4j server."
        ) from exc

    except Exception as exc:
        raise Neo4jConnectionError(
            "Unexpected error while connecting to Neo4j."
        ) from exc