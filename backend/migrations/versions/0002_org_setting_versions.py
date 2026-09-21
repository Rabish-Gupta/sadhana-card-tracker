"""Add versioned organization-wide temporal settings.

Revision ID: 0002_org_setting_versions
Revises: 0001_initial_schema
Create Date: 2026-09-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_org_setting_versions"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # version_status was created by 0001 and is shared by all versioned configuration.
    version_status = postgresql.ENUM(
        "PENDING",
        "ACTIVE",
        "ARCHIVED",
        name="version_status",
        create_type=False,
    )

    op.create_table(
        "organization_setting_versions",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("effective_from_week", sa.Date(), nullable=False),
        sa.Column("status", version_status, nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("week_start_day", sa.SmallInteger(), nullable=False),
        sa.Column("daily_finalize_time", sa.Time(), nullable=False),
        sa.Column("promotion_month", sa.SmallInteger(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "promotion_month BETWEEN 1 AND 12",
            name="ck_organization_setting_versions_promotion_month",
        ),
        sa.CheckConstraint(
            "version_number >= 1",
            name="ck_organization_setting_versions_number",
        ),
        sa.CheckConstraint(
            "week_start_day BETWEEN 0 AND 6",
            name="ck_organization_setting_versions_week_start_day",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "effective_from_week",
            name="uq_organization_setting_versions_effective_week",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "version_number",
            name="uq_organization_setting_versions_number",
        ),
    )
    op.create_index(
        "ix_organization_setting_versions_effective",
        "organization_setting_versions",
        ["organization_id", "effective_from_week"],
        unique=False,
    )
    op.create_index(
        "ix_organization_setting_versions_status",
        "organization_setting_versions",
        ["status"],
        unique=False,
    )

    # Existing organizations predate this table.  Backfill one ACTIVE baseline snapshot
    # from the settings already stored on organizations.  Its effective week is the
    # organization-local week containing the organization's creation timestamp, so the
    # baseline is eligible for every week in which that organization could have existed.
    op.execute(
        """
        INSERT INTO organization_setting_versions (
            id,
            organization_id,
            version_number,
            effective_from_week,
            status,
            timezone,
            week_start_day,
            daily_finalize_time,
            promotion_month,
            created_by_id,
            created_at
        )
        SELECT
            gen_random_uuid(),
            o.id,
            1,
            (
                timezone(o.timezone, o.created_at)::date
                - (
                    (
                        EXTRACT(DOW FROM timezone(o.timezone, o.created_at))::integer
                        - o.week_start_day
                        + 7
                    ) % 7
                )
            ),
            'ACTIVE'::version_status,
            o.timezone,
            o.week_start_day,
            o.daily_finalize_time,
            o.promotion_month,
            NULL,
            o.created_at
        FROM organizations AS o
        WHERE NOT EXISTS (
            SELECT 1
            FROM organization_setting_versions AS osv
            WHERE osv.organization_id = o.id
        )
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_setting_versions_status",
        table_name="organization_setting_versions",
    )
    op.drop_index(
        "ix_organization_setting_versions_effective",
        table_name="organization_setting_versions",
    )
    op.drop_table("organization_setting_versions")
