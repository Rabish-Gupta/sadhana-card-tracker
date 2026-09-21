from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    AggregationMethod,
    RuleType,
    ScoringType,
    StandardPeriod,
    VersionStatus,
)
from app.models.activity import Activity, ActivityField
from app.models.daily_card import DailyActivityEntry, DailyActivityValue
from app.models.evaluation_config import CategoryActivityConfig
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import StandardVersion
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation
from app.schemas.configuration import ActivityFieldUpdateRequest
from app.schemas.historical_correction import HistoricalCardCorrectionRequest
from app.services.configuration import (
    ConfigurationValidationError,
    validate_standard_target_definition,
)
from app.services.weekly_evaluations import _build_activity_result


def test_step12_historical_correction_routes_are_exposed() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}",
    }.issubset(paths)
    operations = app.openapi()["paths"][
        "/api/v1/admin/corrections/devotees/{user_id}/cards/{card_date}"
    ]
    assert {"get", "patch"}.issubset(operations)


def test_historical_card_correction_requires_reason_and_rejects_duplicates() -> None:
    activity_id = uuid.uuid4()
    field_id = uuid.uuid4()
    value = {
        "activity_id": str(activity_id),
        "values": [
            {
                "field_id": str(field_id),
                "is_filled": True,
                "numeric_value": 120,
            }
        ],
    }
    with pytest.raises(ValidationError):
        HistoricalCardCorrectionRequest(reason="  ", activities=[value])
    with pytest.raises(ValidationError):
        HistoricalCardCorrectionRequest(
            reason="Admin correction",
            activities=[value, value],
        )


def test_activity_field_semantics_cannot_be_mutated_in_place() -> None:
    presentation = ActivityFieldUpdateRequest(label="Updated label", display_order=4)
    assert presentation.label == "Updated label"
    with pytest.raises(ValidationError):
        ActivityFieldUpdateRequest(required_for_completion=False)
    with pytest.raises(ValidationError):
        ActivityFieldUpdateRequest(input_type="COUNT")
    with pytest.raises(ValidationError):
        ActivityFieldUpdateRequest()


@pytest.mark.parametrize(
    ("period", "definition"),
    [
        (StandardPeriod.DAILY, {"kind": "BOOLEAN", "value": True, "operator": "="}),
        (StandardPeriod.DAILY, {"kind": "TIME", "value": "03:40", "operator": "<"}),
        (
            StandardPeriod.DAILY,
            {"kind": "DURATION", "value": 120, "unit": "MINUTE", "operator": ">="},
        ),
        (
            StandardPeriod.WEEKLY,
            {"kind": "DURATION", "value": 300, "unit": "MINUTE", "operator": ">="},
        ),
    ],
)
def test_standard_target_definition_accepts_engine_supported_shapes(period, definition) -> None:
    validate_standard_target_definition(period, definition)


@pytest.mark.parametrize(
    ("period", "definition"),
    [
        (StandardPeriod.DAILY, {"kind": "BOOLEAN", "value": "yes", "operator": "="}),
        (StandardPeriod.DAILY, {"kind": "TIME", "value": "not-a-time", "operator": "<"}),
        (StandardPeriod.DAILY, {"kind": "COUNT", "value": 1.5, "operator": ">="}),
        (StandardPeriod.DAILY, {"kind": "DURATION", "value": -1, "operator": ">="}),
        (StandardPeriod.WEEKLY, {"kind": "BOOLEAN", "value": True, "operator": "="}),
        (StandardPeriod.DAILY, {"kind": "DURATION", "value": 60, "operator": "!="}),
        (StandardPeriod.DAILY, {"value": 60, "operator": ">="}),
    ],
)
def test_standard_target_definition_rejects_unexecutable_shapes(period, definition) -> None:
    with pytest.raises(ConfigurationValidationError):
        validate_standard_target_definition(period, definition)


def _weekly_percentage_fixture():
    org_id = uuid.uuid4()
    activity_id = uuid.uuid4()
    config_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    rule_version_id = uuid.uuid4()
    standard_version_id = uuid.uuid4()

    activity = Activity(
        id=activity_id,
        organization_id=org_id,
        code="BOOK_READING",
        name="Book Reading",
        category=ActivityCategory.SADHANA,
        is_system_derived=False,
        is_active=True,
        is_archived=False,
    )
    field = ActivityField(
        id=uuid.uuid4(),
        activity_id=activity_id,
        field_key="minutes",
        label="Book Reading",
        input_type=ActivityInputType.DURATION,
        unit_code="MINUTE",
        display_order=1,
        required_for_completion=True,
        is_active=True,
        is_archived=False,
    )
    config = CategoryActivityConfig(
        id=config_id,
        organization_id=org_id,
        category_id=uuid.uuid4(),
        activity_id=activity_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        is_applicable=True,
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        weekly_aggregation=AggregationMethod.SUM,
        scoring_rule_id=rule_id,
        standard_id=uuid.uuid4(),
        counts_toward_card_fill=True,
        status=VersionStatus.ACTIVE,
        created_by_id=uuid.uuid4(),
    )
    config.activity = activity

    rule = ScoringRule(
        id=rule_id,
        organization_id=org_id,
        activity_id=activity_id,
        name="Book percentage",
        rule_type=RuleType.PERCENTAGE,
        is_active=True,
        is_archived=False,
        created_by_id=uuid.uuid4(),
    )
    rule_version = ScoringRuleVersion(
        id=rule_version_id,
        scoring_rule_id=rule_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        status=VersionStatus.ARCHIVED,
        max_score=490,
        configuration={
            "formula": "STANDARD_PERCENTAGE_X_MAX_SCORE",
            "cap_percentage": 100,
            "rounding": "HALF_UP",
        },
        created_by_id=uuid.uuid4(),
    )
    rule_version.scoring_rule = rule

    standard_version = StandardVersion(
        id=standard_version_id,
        standard_id=config.standard_id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        period=StandardPeriod.WEEKLY,
        target_definition={
            "kind": "DURATION",
            "value": 300,
            "unit": "MINUTE",
            "operator": ">=",
        },
        status=VersionStatus.ARCHIVED,
        created_by_id=uuid.uuid4(),
    )

    entries = []
    for _ in range(7):
        entry = DailyActivityEntry(
            id=uuid.uuid4(),
            daily_card_id=uuid.uuid4(),
            activity_id=activity_id,
            category_activity_config_id=config_id,
            is_filled=True,
            daily_score=None,
            rule_version_id=None,
            max_score_snapshot=None,
        )
        entry.activity = activity
        entry.category_activity_config = config
        value = DailyActivityValue(
            id=uuid.uuid4(),
            daily_activity_entry_id=entry.id,
            activity_field_id=field.id,
            is_filled=True,
            numeric_value=Decimal("50"),
        )
        value.activity_field = field
        entry.values = [value]
        entries.append(entry)

    evaluation = WeeklyEvaluation(
        id=uuid.uuid4(),
        organization_id=org_id,
        devotee_profile_id=uuid.uuid4(),
        week_start_date=date(2026, 9, 14),
        week_end_date=date(2026, 9, 20),
        category_snapshot_id=config.category_id,
        timezone_snapshot="Asia/Kolkata",
        sadhana_score=0,
        sadhana_max_score=0,
        academic_score=0,
        academic_max_score=0,
        revision_number=0,
    )
    historical = WeeklyActivityResult(
        id=uuid.uuid4(),
        weekly_evaluation_id=evaluation.id,
        activity_id=activity_id,
        category_activity_config_id=config_id,
        aggregation_method=AggregationMethod.SUM.value,
        raw_total=Decimal("300"),
        daily_score_total=None,
        final_activity_score=490,
        maximum_score=490,
        rule_version_id=rule_version_id,
        standard_version_id=standard_version_id,
    )
    historical.rule_version = rule_version
    historical.standard_version = standard_version
    return evaluation, entries, historical


def test_weekly_historical_recalculation_uses_stored_rule_and_standard_without_resolution() -> None:
    evaluation, entries, historical = _weekly_percentage_fixture()

    # A plain object is intentionally supplied instead of a DB session.  If the historical
    # path tries to resolve today's rule/standard, this test will fail with AttributeError.
    result = asyncio.run(
        _build_activity_result(
            object(),
            weekly_evaluation=evaluation,
            entries=entries,
            week_start=evaluation.week_start_date,
            historical_snapshot=historical,
        )
    )
    assert result.raw_total == Decimal("350.00")
    assert result.final_activity_score == 490
    assert result.rule_version_id == historical.rule_version_id
    assert result.standard_version_id == historical.standard_version_id
    assert result.standard_achievement == Decimal("116.67")


def test_historical_correction_service_preserves_stored_refs_and_audits_recalculation() -> None:
    source = Path("app/services/historical_corrections.py").read_text()
    assert "_apply_daily_scores(card" in source
    assert "recalculate_existing_weekly_evaluation" in source
    assert 'action="HISTORICAL_CARD_CORRECTED"' in source
    assert 'action="WEEKLY_EVALUATION_RECALCULATED"' in source
    assert "card.revision_number += 1" in source


def test_step12_keeps_existing_schema_and_migration_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.db.base import Base
    import app.models  # noqa: F401

    assert len(Base.metadata.tables) == 19
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_current_head() == "0003_lifecycle_fields"

class _ScalarSession:
    def __init__(self, values):
        self.values = list(values)

    async def scalar(self, statement):
        if not self.values:
            raise AssertionError("Unexpected scalar query")
        return self.values.pop(0)


async def _run_standard_field_validation(activity: Activity, standard_activity_id, definition):
    from app.models.standard import Standard
    from app.services.configuration_admin import _validate_standard_version_definition

    standard = Standard(
        id=uuid.uuid4(),
        organization_id=activity.organization_id,
        activity_id=standard_activity_id,
        name="Test Standard",
        is_active=True,
        is_archived=False,
        created_by_id=uuid.uuid4(),
    )
    session = _ScalarSession([activity])
    await _validate_standard_version_definition(
        session,
        standard=standard,
        period=StandardPeriod.DAILY,
        target_definition=definition,
    )


def test_standard_definition_must_resolve_to_real_activity_field() -> None:
    from app.services.configuration_admin import ConfigurationAdminError

    activity = Activity(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code="CUSTOM",
        name="Custom",
        category=ActivityCategory.ACADEMIC,
        is_system_derived=False,
        is_active=True,
        is_archived=False,
    )
    activity.fields = [
        ActivityField(
            id=uuid.uuid4(),
            activity_id=activity.id,
            field_key="minutes",
            label="Minutes",
            input_type=ActivityInputType.DURATION,
            unit_code="MINUTE",
            display_order=1,
            required_for_completion=True,
            is_active=True,
            is_archived=False,
        )
    ]
    asyncio.run(
        _run_standard_field_validation(
            activity,
            activity.id,
            {"kind": "DURATION", "value": 60, "unit": "MINUTE", "operator": ">="},
        )
    )
    with pytest.raises(ConfigurationAdminError):
        asyncio.run(
            _run_standard_field_validation(
                activity,
                activity.id,
                {
                    "kind": "COUNT",
                    "value": 1,
                    "operator": ">=",
                    "field_key": "missing_count",
                },
            )
        )


def test_system_derived_standard_allows_daily_boolean_without_raw_field() -> None:
    activity = Activity(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code="SYSTEM",
        name="System",
        category=ActivityCategory.ACADEMIC,
        is_system_derived=True,
        is_active=True,
        is_archived=False,
    )
    activity.fields = []
    asyncio.run(
        _run_standard_field_validation(
            activity,
            activity.id,
            {"kind": "BOOLEAN", "value": True, "operator": "="},
        )
    )


def test_activation_has_dependency_preflight_before_status_mutation() -> None:
    source = Path("app/services/configuration_admin.py").read_text()
    preflight = source.index("# Preflight the entire due batch")
    first_mutation = source.index("old.status = VersionStatus.ARCHIVED", preflight)
    assert source.index("_preflight_category_config_activation", preflight) < first_mutation
    assert source.index("_validate_standard_version_definition", preflight) < first_mutation
    assert source.index("_validate_executable_rule_version", preflight) < first_mutation


def test_non_scored_category_config_still_requires_weekly_raw_aggregation() -> None:
    from app.models.evaluation_config import CategoryActivityConfig
    from app.services.configuration import validate_category_activity_config

    config = CategoryActivityConfig(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        activity_id=uuid.uuid4(),
        version_number=1,
        effective_from_week=date(2026, 9, 21),
        is_applicable=True,
        scoring_type=ScoringType.NON_SCORED,
        weekly_aggregation=None,
        scoring_rule_id=None,
        standard_id=None,
        counts_toward_card_fill=True,
        status=VersionStatus.PENDING,
        created_by_id=uuid.uuid4(),
    )
    with pytest.raises(ConfigurationValidationError):
        validate_category_activity_config(config, scoring_rule=None, standard=None)


def test_every_seeded_standard_uses_supported_target_definition() -> None:
    from app.db.seed_data import ACTIVITY_SEEDS

    for activity in ACTIVITY_SEEDS:
        if activity.standard is not None:
            validate_standard_target_definition(
                activity.standard.period,
                activity.standard.target_definition,
            )


def test_historical_category_correction_routes_are_exposed() -> None:
    from app.main import app

    paths = app.openapi()["paths"]
    history_path = "/api/v1/admin/corrections/devotees/{user_id}/category-history"
    correction_path = "/api/v1/admin/corrections/devotees/{user_id}/category"
    assert "get" in paths[history_path]
    assert "patch" in paths[correction_path]


def test_historical_category_correction_request_normalizes_code_and_requires_reason() -> None:
    from app.schemas.historical_correction import HistoricalCategoryCorrectionRequest

    payload = HistoricalCategoryCorrectionRequest(
        effective_from_week=date(2026, 9, 14),
        target_category_code=" yudhishthira ",
        reason=" Correct wrong historical stage ",
    )
    assert payload.target_category_code == "YUDHISHTHIRA"
    assert payload.reason == "Correct wrong historical stage"
    with pytest.raises(ValidationError):
        HistoricalCategoryCorrectionRequest(
            effective_from_week=date(2026, 9, 14),
            target_category_code="ARJUNA",
            reason=" ",
        )


def test_policy_b_category_correction_rebuilds_history_cards_and_weeks() -> None:
    source = Path("app/services/historical_corrections.py").read_text()
    # Policy B: target remains effective until the next different transition.
    assert "Policy B" in source
    assert "row.new_category_id == target_category.id" in source
    assert "row.previous_category_id = target_category.id" in source
    # Corrected historical cards resolve the category configuration/rules for that week,
    # and existing weekly results are rebuilt rather than reusing the wrong category refs.
    assert "_resolve_category_configs(" in source
    assert "_resolve_rule_versions(" in source
    assert "rebuild_existing_weekly_evaluation_for_category_correction" in source
    assert 'action="HISTORICAL_CATEGORY_CORRECTED"' in source
    assert 'action="HISTORICAL_CARD_CATEGORY_REBUILT"' in source
    assert 'action="WEEKLY_EVALUATION_CATEGORY_REBUILT"' in source


def test_category_correction_weekly_rebuild_allows_category_activity_set_change() -> None:
    source = Path("app/services/weekly_evaluations.py").read_text()
    start = source.index("async def rebuild_existing_weekly_evaluation_for_category_correction")
    end = source.index("async def load_existing_weekly_evaluation_public", start)
    body = source[start:end]
    assert "for row in list(evaluation.activity_results)" in body
    assert "await session.delete(row)" in body
    assert "historical_snapshot=" not in body
    assert "evaluation.category_snapshot_id = category_id" in body


def test_audit_json_conversion_is_recursive_for_category_correction_snapshots() -> None:
    from datetime import datetime, timezone
    from app.services.audit import _json_safe

    identifier = uuid.uuid4()
    converted = _json_safe(
        {
            "nested": {
                "ids": [identifier],
                "week": date(2026, 9, 14),
                "amount": Decimal("12.50"),
                "at": datetime(2026, 9, 14, tzinfo=timezone.utc),
            }
        }
    )
    assert converted == {
        "nested": {
            "ids": [str(identifier)],
            "week": "2026-09-14",
            "amount": "12.50",
            "at": "2026-09-14T00:00:00+00:00",
        }
    }
