from neo4j import GraphDatabase

from app.infra.neo4j.config import neo4j_config


neo4j_driver = GraphDatabase.driver(
    neo4j_config.uri,
    auth=(
        neo4j_config.username,
        neo4j_config.password,
    ),
)