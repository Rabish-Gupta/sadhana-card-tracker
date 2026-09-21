"""Add pending lifecycle deactivation fields.

Revision ID: 0003_lifecycle_fields
Revises: 0002_org_setting_versions
Create Date: 2026-09-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_lifecycle_fields"
down_revision: Union[str, None] = "0002_org_setting_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("pending_deactivation_week", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("pending_deactivation_reason", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("pending_deactivation_requested_by_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("pending_deactivation_scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_pending_deactivation_requested_by",
        "users",
        "users",
        ["pending_deactivation_requested_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_users_pending_deactivation_week",
        "users",
        ["pending_deactivation_week"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_users_pending_deactivation_week", table_name="users")
    op.drop_constraint(
        "fk_users_pending_deactivation_requested_by",
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "pending_deactivation_scheduled_at")
    op.drop_column("users", "pending_deactivation_requested_by_id")
    op.drop_column("users", "pending_deactivation_reason")
    op.drop_column("users", "pending_deactivation_week")
