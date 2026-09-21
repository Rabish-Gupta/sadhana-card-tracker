"""Initial PostgreSQL schema for the Sadhana Card Tracker.

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-09-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Database-wide extensions required by the approved PostgreSQL design.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table('organizations',
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('timezone', sa.String(length=64), nullable=False),
    sa.Column('week_start_day', sa.SmallInteger(), nullable=False),
    sa.Column('daily_finalize_time', sa.Time(), nullable=False),
    sa.Column('promotion_month', sa.SmallInteger(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('promotion_month BETWEEN 1 AND 12', name='ck_organizations_promotion_month'),
    sa.CheckConstraint('week_start_day BETWEEN 0 AND 6', name='ck_organizations_week_start_day'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code', name='uq_organizations_code')
    )
    op.create_table('activities',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('category', sa.Enum('SADHANA', 'ACADEMIC', name='activity_category'), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_system_derived', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'code', name='uq_activities_org_code')
    )
    op.create_index('ix_activities_org_category_active', 'activities', ['organization_id', 'category', 'is_active'], unique=False)
    op.create_table('devotee_categories',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('code', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('academic_year', sa.SmallInteger(), nullable=True),
    sa.Column('stage_order', sa.SmallInteger(), nullable=False),
    sa.Column('employment_status', sa.Enum('WORKING', 'NOT_WORKING', name='employment_status'), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('academic_year IS NULL OR academic_year BETWEEN 1 AND 4', name='ck_devotee_categories_academic_year'),
    sa.CheckConstraint('stage_order >= 1', name='ck_devotee_categories_stage_order'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'code', name='uq_devotee_categories_org_code')
    )
    op.create_index('ix_devotee_categories_org_active', 'devotee_categories', ['organization_id', 'is_active'], unique=False)
    op.create_table('users',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('phone_number', sa.String(length=30), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('role', sa.Enum('DEVOTEE', 'ADMIN', name='user_role'), nullable=False),
    sa.Column('account_status', sa.Enum('PENDING', 'ACTIVE', 'INACTIVE', 'REJECTED', name='account_status'), nullable=False),
    sa.Column('registration_source', sa.Enum('SELF_REGISTERED', 'ADMIN_CREATED', name='registration_source'), nullable=False),
    sa.Column('approved_by_id', sa.Uuid(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organization_id', 'email', name='uq_users_org_email')
    )
    op.create_index('ix_users_org_status', 'users', ['organization_id', 'account_status'], unique=False)
    op.create_table('activity_fields',
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('field_key', sa.String(length=60), nullable=False),
    sa.Column('label', sa.String(length=150), nullable=False),
    sa.Column('input_type', sa.Enum('NUMBER', 'COUNT', 'DURATION', 'TIME', 'BOOLEAN', 'TEXT', 'SELECTION', name='activity_input_type'), nullable=False),
    sa.Column('unit_code', sa.String(length=30), nullable=True),
    sa.Column('display_order', sa.SmallInteger(), nullable=False),
    sa.Column('required_for_completion', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'field_key', name='uq_activity_fields_key')
    )
    op.create_index('ix_activity_fields_activity_active', 'activity_fields', ['activity_id', 'is_active'], unique=False)
    op.create_table('audit_logs',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('entity_type', sa.String(length=60), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('action', sa.String(length=80), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('before_data', postgresql.JSONB(), nullable=True),
    sa.Column('after_data', postgresql.JSONB(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_created', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_entity', 'audit_logs', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_audit_org_created', 'audit_logs', ['organization_id', 'created_at'], unique=False)
    op.create_table('devotee_profiles',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('current_category_id', sa.Uuid(), nullable=False),
    sa.Column('college', sa.String(length=200), nullable=False),
    sa.Column('branch', sa.String(length=120), nullable=False),
    sa.Column('college_joining_year', sa.SmallInteger(), nullable=False),
    sa.Column('expected_graduation_year', sa.SmallInteger(), nullable=True),
    sa.Column('current_academic_year', sa.SmallInteger(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('current_academic_year IS NULL OR current_academic_year BETWEEN 1 AND 4', name='ck_devotee_profiles_current_academic_year'),
    sa.ForeignKeyConstraint(['current_category_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_index('ix_devotee_profiles_category', 'devotee_profiles', ['current_category_id'], unique=False)
    op.create_table('scoring_rules',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('rule_type', sa.Enum('BOOLEAN', 'THRESHOLD', 'PERCENTAGE', 'SYSTEM_DERIVED', 'NO_SCORE', name='rule_type'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_scoring_rules_org_active', 'scoring_rules', ['organization_id', 'is_active'], unique=False)
    op.create_index('ix_scoring_rules_org_activity', 'scoring_rules', ['organization_id', 'activity_id'], unique=False)
    op.create_table('standards',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_archived', sa.Boolean(), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_standards_org_active', 'standards', ['organization_id', 'is_active'], unique=False)
    op.create_index('ix_standards_org_activity', 'standards', ['organization_id', 'activity_id'], unique=False)
    op.create_table('category_activity_configs',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('effective_from_week', sa.Date(), nullable=False),
    sa.Column('is_applicable', sa.Boolean(), nullable=False),
    sa.Column('scoring_type', sa.Enum('DAILY', 'WEEKLY_AGGREGATED', 'NON_SCORED', 'SYSTEM_DERIVED', name='scoring_type'), nullable=False),
    sa.Column('weekly_aggregation', sa.Enum('SUM', 'AVERAGE', 'COUNT', 'MIN', 'MAX', name='aggregation_method'), nullable=True),
    sa.Column('scoring_rule_id', sa.Uuid(), nullable=True),
    sa.Column('standard_id', sa.Uuid(), nullable=True),
    sa.Column('counts_toward_card_fill', sa.Boolean(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'ARCHIVED', name='version_status'), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version_number >= 1', name='ck_category_activity_configs_version'),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['scoring_rule_id'], ['scoring_rules.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['standard_id'], ['standards.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('category_id', 'activity_id', 'effective_from_week', name='uq_category_activity_configs_effective_week'),
    sa.UniqueConstraint('category_id', 'activity_id', 'version_number', name='uq_category_activity_configs_version')
    )
    op.create_index('ix_category_activity_configs_effective', 'category_activity_configs', ['category_id', 'activity_id', 'effective_from_week'], unique=False)
    op.create_index('ix_category_activity_configs_org', 'category_activity_configs', ['organization_id'], unique=False)
    op.create_index('ix_category_activity_configs_status', 'category_activity_configs', ['status'], unique=False)
    op.create_table('daily_cards',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('devotee_profile_id', sa.Uuid(), nullable=False),
    sa.Column('card_date', sa.Date(), nullable=False),
    sa.Column('category_snapshot_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('IN_PROGRESS', 'FINALIZED', name='card_status'), nullable=False),
    sa.Column('first_update_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_update_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('timezone_snapshot', sa.Text(), nullable=False),
    sa.Column('deadline_time_snapshot', sa.Time(), nullable=False),
    sa.Column('deadline_at_utc', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('revision_number >= 0', name='ck_daily_cards_revision'),
    sa.ForeignKeyConstraint(['category_snapshot_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['devotee_profile_id'], ['devotee_profiles.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('devotee_profile_id', 'card_date', name='uq_daily_cards_devotee_date')
    )
    op.create_index('ix_daily_cards_devotee_date', 'daily_cards', ['devotee_profile_id', 'card_date'], unique=False)
    op.create_index('ix_daily_cards_finalize', 'daily_cards', ['status', 'deadline_at_utc'], unique=False)
    op.create_index('ix_daily_cards_org_date', 'daily_cards', ['organization_id', 'card_date'], unique=False)
    op.create_table('devotee_category_history',
    sa.Column('devotee_profile_id', sa.Uuid(), nullable=False),
    sa.Column('previous_category_id', sa.Uuid(), nullable=True),
    sa.Column('new_category_id', sa.Uuid(), nullable=False),
    sa.Column('effective_from_week', sa.Date(), nullable=False),
    sa.Column('change_source', sa.Enum('SYSTEM', 'ADMIN', 'DEVOTEE', name='change_source'), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('changed_by_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('previous_category_id IS NULL OR previous_category_id <> new_category_id', name='ck_category_history_changed_category'),
    sa.UniqueConstraint('devotee_profile_id', 'effective_from_week', name='uq_category_history_profile_effective'),
    sa.ForeignKeyConstraint(['changed_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['devotee_profile_id'], ['devotee_profiles.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['new_category_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['previous_category_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_category_history_profile_effective', 'devotee_category_history', ['devotee_profile_id', 'effective_from_week'], unique=False)
    op.create_table('scoring_rule_versions',
    sa.Column('scoring_rule_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('effective_from_week', sa.Date(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'ARCHIVED', name='version_status'), nullable=False),
    sa.Column('max_score', sa.Integer(), nullable=False),
    sa.Column('rounding_mode', sa.Enum('HALF_UP', name='rounding_mode'), nullable=False),
    sa.Column('configuration', postgresql.JSONB(), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('max_score >= 0', name='ck_scoring_rule_versions_max_score'),
    sa.CheckConstraint('version_number >= 1', name='ck_scoring_rule_versions_number'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['scoring_rule_id'], ['scoring_rules.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scoring_rule_id', 'effective_from_week', name='uq_scoring_rule_versions_effective_week'),
    sa.UniqueConstraint('scoring_rule_id', 'version_number', name='uq_scoring_rule_versions_number')
    )
    op.create_index('ix_scoring_rule_versions_effective', 'scoring_rule_versions', ['scoring_rule_id', 'effective_from_week'], unique=False)
    op.create_index('ix_scoring_rule_versions_status', 'scoring_rule_versions', ['status'], unique=False)
    op.create_table('standard_versions',
    sa.Column('standard_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('effective_from_week', sa.Date(), nullable=False),
    sa.Column('period', sa.Enum('DAILY', 'WEEKLY', name='standard_period'), nullable=False),
    sa.Column('target_definition', postgresql.JSONB(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'ACTIVE', 'ARCHIVED', name='version_status'), nullable=False),
    sa.Column('created_by_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version_number >= 1', name='ck_standard_versions_number'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['standard_id'], ['standards.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('standard_id', 'effective_from_week', name='uq_standard_versions_effective_week'),
    sa.UniqueConstraint('standard_id', 'version_number', name='uq_standard_versions_number')
    )
    op.create_index('ix_standard_versions_effective', 'standard_versions', ['standard_id', 'effective_from_week'], unique=False)
    op.create_index('ix_standard_versions_status', 'standard_versions', ['status'], unique=False)
    op.create_table('weekly_evaluations',
    sa.Column('organization_id', sa.Uuid(), nullable=False),
    sa.Column('devotee_profile_id', sa.Uuid(), nullable=False),
    sa.Column('week_start_date', sa.Date(), nullable=False),
    sa.Column('week_end_date', sa.Date(), nullable=False),
    sa.Column('category_snapshot_id', sa.Uuid(), nullable=False),
    sa.Column('timezone_snapshot', sa.String(length=64), nullable=False),
    sa.Column('sadhana_score', sa.Integer(), nullable=False),
    sa.Column('sadhana_max_score', sa.Integer(), nullable=False),
    sa.Column('sadhana_percentage', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('academic_score', sa.Integer(), nullable=False),
    sa.Column('academic_max_score', sa.Integer(), nullable=False),
    sa.Column('academic_percentage', sa.Numeric(precision=6, scale=2), nullable=True),
    sa.Column('revision_number', sa.Integer(), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('academic_max_score >= 0', name='ck_weekly_eval_academic_max'),
    sa.CheckConstraint('academic_score >= 0', name='ck_weekly_eval_academic_score'),
    sa.CheckConstraint('revision_number >= 0', name='ck_weekly_eval_revision'),
    sa.CheckConstraint('sadhana_max_score >= 0', name='ck_weekly_eval_sadhana_max'),
    sa.CheckConstraint('sadhana_score >= 0', name='ck_weekly_eval_sadhana_score'),
    sa.CheckConstraint('week_end_date >= week_start_date', name='ck_weekly_eval_dates'),
    sa.ForeignKeyConstraint(['category_snapshot_id'], ['devotee_categories.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['devotee_profile_id'], ['devotee_profiles.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('devotee_profile_id', 'week_start_date', name='uq_weekly_evaluations_devotee_week')
    )
    op.create_index('ix_weekly_devotee_week', 'weekly_evaluations', ['devotee_profile_id', 'week_start_date'], unique=False)
    op.create_index('ix_weekly_org_week', 'weekly_evaluations', ['organization_id', 'week_start_date'], unique=False)
    op.create_table('daily_activity_entries',
    sa.Column('daily_card_id', sa.Uuid(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('category_activity_config_id', sa.Uuid(), nullable=False),
    sa.Column('is_filled', sa.Boolean(), nullable=False),
    sa.Column('daily_score', sa.Integer(), nullable=True),
    sa.Column('rule_version_id', sa.Uuid(), nullable=True),
    sa.Column('max_score_snapshot', sa.Integer(), nullable=True),
    sa.Column('score_calculated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('score_details', postgresql.JSONB(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.CheckConstraint('daily_score IS NULL OR daily_score >= 0', name='ck_daily_activity_entries_score'),
    sa.CheckConstraint('max_score_snapshot IS NULL OR max_score_snapshot >= 0', name='ck_daily_activity_entries_max_score'),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_activity_config_id'], ['category_activity_configs.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['daily_card_id'], ['daily_cards.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rule_version_id'], ['scoring_rule_versions.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('daily_card_id', 'activity_id', name='uq_daily_activity_entries_card_activity')
    )
    op.create_index('ix_daily_activity_entries_activity', 'daily_activity_entries', ['activity_id'], unique=False)
    op.create_index('ix_daily_activity_entries_card', 'daily_activity_entries', ['daily_card_id'], unique=False)
    op.create_table('weekly_activity_results',
    sa.Column('weekly_evaluation_id', sa.Uuid(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('category_activity_config_id', sa.Uuid(), nullable=False),
    sa.Column('aggregation_method', sa.String(length=20), nullable=True),
    sa.Column('raw_total', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('daily_score_total', sa.Integer(), nullable=True),
    sa.Column('final_activity_score', sa.Integer(), nullable=True),
    sa.Column('maximum_score', sa.Integer(), nullable=True),
    sa.Column('rule_version_id', sa.Uuid(), nullable=True),
    sa.Column('standard_version_id', sa.Uuid(), nullable=True),
    sa.Column('standard_snapshot', postgresql.JSONB(), nullable=True),
    sa.Column('standard_achievement', sa.Numeric(precision=7, scale=2), nullable=True),
    sa.Column('calculation_details', postgresql.JSONB(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('daily_score_total IS NULL OR daily_score_total >= 0', name='ck_weekly_activity_results_daily_score'),
    sa.CheckConstraint('final_activity_score IS NULL OR final_activity_score >= 0', name='ck_weekly_activity_results_final_score'),
    sa.CheckConstraint('maximum_score IS NULL OR maximum_score >= 0', name='ck_weekly_activity_results_maximum'),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['category_activity_config_id'], ['category_activity_configs.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['rule_version_id'], ['scoring_rule_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['standard_version_id'], ['standard_versions.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['weekly_evaluation_id'], ['weekly_evaluations.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('weekly_evaluation_id', 'activity_id', name='uq_weekly_activity_results_eval_activity')
    )
    op.create_index('ix_weekly_activity_results_activity', 'weekly_activity_results', ['activity_id'], unique=False)
    op.create_index('ix_weekly_activity_results_eval', 'weekly_activity_results', ['weekly_evaluation_id'], unique=False)
    op.create_table('daily_activity_values',
    sa.Column('daily_activity_entry_id', sa.Uuid(), nullable=False),
    sa.Column('activity_field_id', sa.Uuid(), nullable=False),
    sa.Column('is_filled', sa.Boolean(), nullable=False),
    sa.Column('numeric_value', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('time_value', sa.Time(), nullable=True),
    sa.Column('boolean_value', sa.Boolean(), nullable=True),
    sa.Column('text_value', sa.Text(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['activity_field_id'], ['activity_fields.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['daily_activity_entry_id'], ['daily_activity_entries.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('daily_activity_entry_id', 'activity_field_id', name='uq_daily_activity_values_entry_field')
    )
    op.create_index('ix_daily_activity_values_entry', 'daily_activity_values', ['daily_activity_entry_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_daily_activity_values_entry', table_name='daily_activity_values')
    op.drop_table('daily_activity_values')
    op.drop_index('ix_weekly_activity_results_eval', table_name='weekly_activity_results')
    op.drop_index('ix_weekly_activity_results_activity', table_name='weekly_activity_results')
    op.drop_table('weekly_activity_results')
    op.drop_index('ix_daily_activity_entries_card', table_name='daily_activity_entries')
    op.drop_index('ix_daily_activity_entries_activity', table_name='daily_activity_entries')
    op.drop_table('daily_activity_entries')
    op.drop_index('ix_weekly_org_week', table_name='weekly_evaluations')
    op.drop_index('ix_weekly_devotee_week', table_name='weekly_evaluations')
    op.drop_table('weekly_evaluations')
    op.drop_index('ix_standard_versions_status', table_name='standard_versions')
    op.drop_index('ix_standard_versions_effective', table_name='standard_versions')
    op.drop_table('standard_versions')
    op.drop_index('ix_scoring_rule_versions_status', table_name='scoring_rule_versions')
    op.drop_index('ix_scoring_rule_versions_effective', table_name='scoring_rule_versions')
    op.drop_table('scoring_rule_versions')
    op.drop_index('ix_category_history_profile_effective', table_name='devotee_category_history')
    op.drop_table('devotee_category_history')
    op.drop_index('ix_daily_cards_org_date', table_name='daily_cards')
    op.drop_index('ix_daily_cards_finalize', table_name='daily_cards')
    op.drop_index('ix_daily_cards_devotee_date', table_name='daily_cards')
    op.drop_table('daily_cards')
    op.drop_index('ix_category_activity_configs_status', table_name='category_activity_configs')
    op.drop_index('ix_category_activity_configs_org', table_name='category_activity_configs')
    op.drop_index('ix_category_activity_configs_effective', table_name='category_activity_configs')
    op.drop_table('category_activity_configs')
    op.drop_index('ix_standards_org_activity', table_name='standards')
    op.drop_index('ix_standards_org_active', table_name='standards')
    op.drop_table('standards')
    op.drop_index('ix_scoring_rules_org_activity', table_name='scoring_rules')
    op.drop_index('ix_scoring_rules_org_active', table_name='scoring_rules')
    op.drop_table('scoring_rules')
    op.drop_index('ix_devotee_profiles_category', table_name='devotee_profiles')
    op.drop_table('devotee_profiles')
    op.drop_index('ix_audit_org_created', table_name='audit_logs')
    op.drop_index('ix_audit_entity', table_name='audit_logs')
    op.drop_index('ix_audit_created', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index('ix_activity_fields_activity_active', table_name='activity_fields')
    op.drop_table('activity_fields')
    op.drop_index('ix_users_org_status', table_name='users')
    op.drop_table('users')
    op.drop_index('ix_devotee_categories_org_active', table_name='devotee_categories')
    op.drop_table('devotee_categories')
    op.drop_index('ix_activities_org_category_active', table_name='activities')
    op.drop_table('activities')
    op.drop_table('organizations')

    # Native PostgreSQL enum types are schema objects and outlive dropped tables.
    postgresql.ENUM(name='card_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='standard_period').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='rounding_mode').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='change_source').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='version_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='aggregation_method').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='scoring_type').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='rule_type').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='activity_input_type').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='registration_source').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='account_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='user_role').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='employment_status').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='activity_category').drop(op.get_bind(), checkfirst=True)

    # pgcrypto/citext are intentionally retained because extensions are database-wide.
