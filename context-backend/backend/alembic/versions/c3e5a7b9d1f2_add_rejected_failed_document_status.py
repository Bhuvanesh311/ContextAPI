"""add REJECTED and FAILED to documentstatus

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-07

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, Sequence[str], None] = 'b2d4f6a8c0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'REJECTED'")
    op.execute("ALTER TYPE documentstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    # Postgres cannot drop enum values; move rows back to INACTIVE instead.
    op.execute(
        "UPDATE documents SET status = 'INACTIVE' "
        "WHERE status::text IN ('REJECTED', 'FAILED')"
    )
