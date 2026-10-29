from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str


neo4j_config = Neo4jConfig(
    uri=settings.NEO4J_URI,
    username=settings.NEO4J_USERNAME,
    password=settings.NEO4J_PASSWORD,
)