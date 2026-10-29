from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class ChromaDBConfig:
    host: str
    port: int
    ssl: bool


chromadb_config = ChromaDBConfig(
    host=settings.CHROMADB_HOST,
    port=settings.CHROMADB_PORT,
    ssl=settings.CHROMADB_SSL,
)