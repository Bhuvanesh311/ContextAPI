"""Add L03 intelligence fields to retrieval_requests

Revision ID: 6444e6485b85
Revises: d3b943afdb25
Create Date: 2026-09-09 16:37:31.390216

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6444e6485b85'
down_revision: Union[str, Sequence[str], None] = 'd3b943afdb25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('retrieval_requests', sa.Column('query_safety_outcome', sa.String(length=50), nullable=True))
    op.add_column('retrieval_requests', sa.Column('query_safety_risk_level', sa.Numeric(), nullable=True))
    op.add_column('retrieval_requests', sa.Column('memory_requirement', sa.String(length=50), nullable=True))

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('retrieval_requests', 'memory_requirement')
    op.drop_column('retrieval_requests', 'query_safety_risk_level')
    op.drop_column('retrieval_requests', 'query_safety_outcome')
