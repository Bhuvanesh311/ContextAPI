"""Fix retrieval_requests primary key (id autoincrement)

Revision ID: a4f8c2d91b6e
Revises: 7a1c9e5b2f30
Create Date: 2026-09-28 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a4f8c2d91b6e'
down_revision: Union[str, Sequence[str], None] = '7a1c9e5b2f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "CREATE SEQUENCE IF NOT EXISTS retrieval_requests_id_seq "
        "OWNED BY retrieval_requests.id"
    )
    op.execute(
        "SELECT setval('retrieval_requests_id_seq', "
        "COALESCE((SELECT MAX(id) FROM retrieval_requests), 0) + 1, false)"
    )
    op.execute(
        "ALTER TABLE retrieval_requests "
        "ALTER COLUMN id SET DEFAULT nextval('retrieval_requests_id_seq')"
    )
    op.drop_constraint('retrieval_requests_pkey', 'retrieval_requests', type_='primary')
    op.create_primary_key('retrieval_requests_pkey', 'retrieval_requests', ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('retrieval_requests_pkey', 'retrieval_requests', type_='primary')
    op.create_primary_key('retrieval_requests_pkey', 'retrieval_requests', ['request_id'])
    op.execute("ALTER TABLE retrieval_requests ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS retrieval_requests_id_seq")