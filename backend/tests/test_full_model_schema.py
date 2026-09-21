from decimal import Decimal

from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.base import Base
from app.models.daily_card import DailyActivityValue


EXPECTED_TABLES = {
    "organizations",
    "organization_setting_versions",
    "users",
    "devotee_categories",
    "devotee_profiles",
    "devotee_category_history",
    "activities",
    "activity_fields",
    "scoring_rules",
    "scoring_rule_versions",
    "standards",
    "standard_versions",
    "category_activity_configs",
    "daily_cards",
    "daily_activity_entries",
    "daily_activity_values",
    "weekly_evaluations",
    "weekly_activity_results",
    "audit_logs",
}


def test_all_approved_application_tables_are_mapped() -> None:
    configure_mappers()
    assert EXPECTED_TABLES == set(Base.metadata.tables)


def test_daily_card_has_unique_devotee_date_constraint() -> None:
    table = Base.metadata.tables["daily_cards"]
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("devotee_profile_id", "card_date") in unique_column_sets


def test_missing_numeric_value_and_intentional_zero_can_be_distinguished() -> None:
    missing = DailyActivityValue(is_filled=False, numeric_value=Decimal("0"))
    intentional_zero = DailyActivityValue(is_filled=True, numeric_value=Decimal("0"))

    assert missing.numeric_value == intentional_zero.numeric_value == Decimal("0")
    assert missing.is_filled is False
    assert intentional_zero.is_filled is True


def test_historical_version_foreign_keys_are_restrictive() -> None:
    entry_table = Base.metadata.tables["daily_activity_entries"]
    weekly_table = Base.metadata.tables["weekly_activity_results"]

    entry_fk = next(
        fk
        for fk in entry_table.foreign_keys
        if fk.parent.name == "rule_version_id"
    )
    weekly_rule_fk = next(
        fk
        for fk in weekly_table.foreign_keys
        if fk.parent.name == "rule_version_id"
    )
    weekly_standard_fk = next(
        fk
        for fk in weekly_table.foreign_keys
        if fk.parent.name == "standard_version_id"
    )

    assert entry_fk.ondelete == "RESTRICT"
    assert weekly_rule_fk.ondelete == "RESTRICT"
    assert weekly_standard_fk.ondelete == "RESTRICT"
