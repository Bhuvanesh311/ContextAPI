"""Add sufficiency column to retrieval_requests (L07)

Revision ID: b7d2e4f6a8c1
Revises: a4f8c2d91b6e
Create Date: 2026-09-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2e4f6a8c1'
down_revision: Union[str, Sequence[str], None] = 'a4f8c2d91b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "retrieval_requests",
        sa.Column("sufficiency", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("retrieval_requests", "sufficiency")
