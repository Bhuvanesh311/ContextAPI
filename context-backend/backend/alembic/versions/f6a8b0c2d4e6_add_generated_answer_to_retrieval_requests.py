"""Add generated_answer column to retrieval_requests

Revision ID: f6a8b0c2d4e6
Revises: e5f7a9b1c3d2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a8b0c2d4e6'
down_revision: Union[str, Sequence[str], None] = 'e5f7a9b1c3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("retrieval_requests", sa.Column("generated_answer", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("retrieval_requests", "generated_answer")
