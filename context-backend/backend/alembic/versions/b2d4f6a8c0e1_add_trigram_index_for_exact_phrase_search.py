"""Trigram index on document_chunks.content for exact-phrase search

The structured (exact phrase) capability filters with ILIKE '%phrase%',
which is a full table scan without a trigram index.

Needs the pg_trgm extension (CREATE EXTENSION requires a role allowed to
create extensions; on managed Postgres enable pg_trgm first).

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_chunks_content_trgm "
        "ON document_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_content_trgm")
