"""Add results column to retrieval_requests

Revision ID: 7a1c9e5b2f30
Revises: 2d853bf18d7c
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7a1c9e5b2f30'
down_revision: Union[str, Sequence[str], None] = '2d853bf18d7c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "retrieval_requests",
        sa.Column("results", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("retrieval_requests", "results")