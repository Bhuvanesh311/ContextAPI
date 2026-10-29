"""Add tenants table and tenant_id to users and projects

Every existing user gets a personal tenant (TEN + the user's sequence digits),
and every existing project joins its owner's tenant, so nobody loses access
and no data is shared between users after the upgrade.

Revision ID: e5f7a9b1c3d2
Revises: c8e3f1a7d2b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f7a9b1c3d2'
down_revision: Union[str, Sequence[str], None] = 'c8e3f1a7d2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("tenant_id", sa.String(length=20), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.add_column("users", sa.Column("tenant_id", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"])
    op.create_foreign_key("fk_users_tenant_id", "users", "tenants", ["tenant_id"], ["tenant_id"])

    op.add_column("projects", sa.Column("tenant_id", sa.String(length=20), nullable=True))
    op.create_index(op.f("ix_projects_tenant_id"), "projects", ["tenant_id"])
    op.create_foreign_key("fk_projects_tenant_id", "projects", "tenants", ["tenant_id"], ["tenant_id"])

    # Backfill: one personal tenant per existing user, projects follow their owner.
    op.execute(
        """
        INSERT INTO tenants (tenant_id, name, created_at)
        SELECT 'TEN' || substr(user_id, 4), username, now() FROM users
        """
    )
    op.execute("UPDATE users SET tenant_id = 'TEN' || substr(user_id, 4)")
    op.execute(
        """
        UPDATE projects SET tenant_id = users.tenant_id
        FROM users WHERE projects.user_id = users.user_id
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_tenant_id", "projects", type_="foreignkey")
    op.drop_index(op.f("ix_projects_tenant_id"), table_name="projects")
    op.drop_column("projects", "tenant_id")

    op.drop_constraint("fk_users_tenant_id", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_column("users", "tenant_id")

    op.drop_table("tenants")