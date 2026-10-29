"""Add idempotency_key to retrieval_requests

Revision ID: d3b943afdb25
Revises: 410e14bb1f8f
Create Date: 2026-09-09 10:52:20.784918

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3b943afdb25'
down_revision: Union[str, Sequence[str], None] = '410e14bb1f8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('retrieval_requests', sa.Column('idempotency_key', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_retrieval_requests_idempotency_key'), 'retrieval_requests', ['idempotency_key'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_retrieval_requests_idempotency_key'), table_name='retrieval_requests')
    op.drop_column('retrieval_requests', 'idempotency_key')