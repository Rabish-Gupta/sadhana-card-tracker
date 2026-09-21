import uuid
from datetime import date

import pytest
from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.core.enums import (
    ActivityCategory,
    AggregationMethod,
    RuleType,
    ScoringType,
    VersionStatus,
)
from app.db.base import Base
from app.models.evaluation_config import CategoryActivityConfig
from app.models.scoring import ScoringRule
from app.models.standard import Standard
from app.services.configuration import (
    ConfigurationValidationError,
    require_week_boundary,
    resolve_latest_effective_version,
    validate_category_activity_config,
)


def test_configuration_tables_are_registered() -> None:
    configure_mappers()
    assert {
        "activities",
        "activity_fields",
        "scoring_rules",
        "scoring_rule_versions",
        "standards",
        "standard_versions",
        "category_activity_configs",
        "organization_setting_versions",
    }.issubset(Base.metadata.tables.keys())


def test_finalized_registration_fields_exist() -> None:
    users = Base.metadata.tables["users"]
    profiles = Base.metadata.tables["devotee_profiles"]

    assert users.c.phone_number.nullable is False
    assert profiles.c.college.nullable is False
    assert profiles.c.branch.nullable is False
    assert profiles.c.college_joining_year.nullable is False


def _rule_and_standard(rule_type: RuleType = RuleType.THRESHOLD):
    organization_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    rule = ScoringRule(
        id=uuid.uuid4(),
        organization_id=organization_id,
        activity_id=activity_id,
        name="Rule",
        rule_type=rule_type,
        created_by_id=creator_id,
    )
    standard = Standard(
        id=uuid.uuid4(),
        organization_id=organization_id,
        activity_id=activity_id,
        name="Standard",
        created_by_id=creator_id,
    )
    return organization_id, activity_id, creator_id, rule, standard


def test_daily_config_requires_rule_and_weekly_aggregation() -> None:
    organization_id, activity_id, creator_id, _, _ = _rule_and_standard()
    config = CategoryActivityConfig(
        id=uuid.uuid4(),
        organization_id=organization_id,
        category_id=uuid.uuid4(),
        activity_id=activity_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        is_applicable=True,
        scoring_type=ScoringType.DAILY,
        weekly_aggregation=AggregationMethod.SUM,
        scoring_rule_id=None,
        standard_id=None,
        counts_toward_card_fill=True,
        status=VersionStatus.PENDING,
        created_by_id=creator_id,
    )

    with pytest.raises(ConfigurationValidationError, match="require a scoring rule"):
        validate_category_activity_config(config, scoring_rule=None, standard=None)


def test_percentage_config_requires_standard() -> None:
    organization_id, activity_id, creator_id, rule, _ = _rule_and_standard(
        RuleType.PERCENTAGE
    )
    config = CategoryActivityConfig(
        id=uuid.uuid4(),
        organization_id=organization_id,
        category_id=uuid.uuid4(),
        activity_id=activity_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        is_applicable=True,
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        weekly_aggregation=AggregationMethod.SUM,
        scoring_rule_id=rule.id,
        standard_id=None,
        counts_toward_card_fill=True,
        status=VersionStatus.PENDING,
        created_by_id=creator_id,
    )

    with pytest.raises(ConfigurationValidationError, match="requires a configured standard"):
        validate_category_activity_config(config, scoring_rule=rule, standard=None)


def test_valid_percentage_config_passes() -> None:
    organization_id, activity_id, creator_id, rule, standard = _rule_and_standard(
        RuleType.PERCENTAGE
    )
    config = CategoryActivityConfig(
        id=uuid.uuid4(),
        organization_id=organization_id,
        category_id=uuid.uuid4(),
        activity_id=activity_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        is_applicable=True,
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        weekly_aggregation=AggregationMethod.SUM,
        scoring_rule_id=rule.id,
        standard_id=standard.id,
        counts_toward_card_fill=True,
        status=VersionStatus.PENDING,
        created_by_id=creator_id,
    )

    validate_category_activity_config(config, scoring_rule=rule, standard=standard)


def test_effective_dates_must_start_on_configured_week_boundary() -> None:
    require_week_boundary(date(2026, 9, 14), 1)  # Monday

    with pytest.raises(ConfigurationValidationError):
        require_week_boundary(date(2026, 9, 16), 1)


class _Version:
    def __init__(self, effective_from_week: date, status: VersionStatus) -> None:
        self.effective_from_week = effective_from_week
        self.status = status


def test_historical_resolution_includes_archived_but_not_pending_versions() -> None:
    old = _Version(date(2026, 9, 7), VersionStatus.ARCHIVED)
    current = _Version(date(2026, 9, 14), VersionStatus.ACTIVE)
    future = _Version(date(2026, 9, 21), VersionStatus.PENDING)

    assert resolve_latest_effective_version([old, current, future], date(2026, 9, 18)) is current
    assert resolve_latest_effective_version([old, current, future], date(2026, 9, 10)) is old


def test_organization_setting_versions_keep_one_version_number_and_effective_week_per_org() -> None:
    table = Base.metadata.tables["organization_setting_versions"]
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("organization_id", "version_number") in unique_column_sets
    assert ("organization_id", "effective_from_week") in unique_column_sets
