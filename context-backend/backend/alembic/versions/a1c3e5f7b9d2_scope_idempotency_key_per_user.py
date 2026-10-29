"""Make retrieval idempotency_key unique per user, not globally

A global unique index let one user block (or probe) another user's key.

Revision ID: a1c3e5f7b9d2
Revises: f6a8b0c2d4e6
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'f6a8b0c2d4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_retrieval_requests_idempotency_key", table_name="retrieval_requests")
    op.create_index("ix_retrieval_requests_idempotency_key", "retrieval_requests", ["idempotency_key"], unique=False)
    op.create_unique_constraint(
        "uq_retrieval_requests_user_idempotency_key",
        "retrieval_requests",
        ["user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_retrieval_requests_user_idempotency_key", "retrieval_requests", type_="unique")
    op.drop_index("ix_retrieval_requests_idempotency_key", table_name="retrieval_requests")
    op.create_index("ix_retrieval_requests_idempotency_key", "retrieval_requests", ["idempotency_key"], unique=True)
