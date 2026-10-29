"""Add evidence_package column to retrieval_requests

Revision ID: c8e3f1a7d2b4
Revises: b7d2e4f6a8c1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c8e3f1a7d2b4'
down_revision: Union[str, Sequence[str], None] = 'b7d2e4f6a8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("retrieval_requests", sa.Column("evidence_package", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("retrieval_requests", "evidence_package")