from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.enums import EmbeddingStatus
from app.knowledge.uploads.models import ChunkEmbedding


class IndexingPersistenceService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def mark_indexed(self, vector_ids: list[str]) -> None:
        if not vector_ids:
            return

        statement = (
            update(ChunkEmbedding)
            .where(ChunkEmbedding.vector_id.in_(vector_ids))
            .values(
                status=EmbeddingStatus.INDEXED,
                indexed_at=datetime.now(timezone.utc),
            )
        )
        self._db.execute(statement)
        self._db.flush()
