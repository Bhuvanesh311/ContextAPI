"""Add full text search to document chunks

Revision ID: 2d853bf18d7c
Revises: 6444e6485b85
Create Date: 2026-09-14 12:31:44.841852

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d853bf18d7c'
down_revision: Union[str, Sequence[str], None] = '6444e6485b85'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE document_chunks ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;")
    op.execute("CREATE INDEX idx_document_chunks_search_vector ON document_chunks USING GIN(search_vector);")

def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_search_vector;")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS search_vector;")
