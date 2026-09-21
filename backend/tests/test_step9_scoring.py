from __future__ import annotations

import uuid
from datetime import date, time
from decimal import Decimal

import pytest

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    RuleType,
    ScoringType,
    VersionStatus,
)
from app.db.seed_data import ACTIVITY_SEEDS
from app.models.activity import Activity, ActivityField
from app.models.daily_card import DailyActivityEntry, DailyActivityValue
from app.models.evaluation_config import CategoryActivityConfig
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.services.scoring import (
    ScoringConfigurationError,
    evaluate_daily_entry,
    validate_rule_configuration,
)


def _entry(
    *,
    code: str,
    scoring_type: ScoringType,
    rule_type: RuleType | None,
    configuration: dict | None,
    max_score: int | None,
    fields: list[tuple[str, ActivityInputType, bool, object]],
    filled: bool = True,
    counts_toward_card_fill: bool = True,
    system_derived: bool = False,
) -> DailyActivityEntry:
    activity = Activity(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        code=code,
        name=code,
        category=ActivityCategory.ACADEMIC,
        is_system_derived=system_derived,
        is_active=True,
        is_archived=False,
    )
    config = CategoryActivityConfig(
        id=uuid.uuid4(),
        organization_id=activity.organization_id,
        category_id=uuid.uuid4(),
        activity_id=activity.id,
        version_number=1,
        effective_from_week=date(2026, 9, 14),
        is_applicable=True,
        scoring_type=scoring_type,
        weekly_aggregation=None,
        scoring_rule_id=None,
        standard_id=None,
        counts_toward_card_fill=counts_toward_card_fill,
        status=VersionStatus.ACTIVE,
        created_by_id=uuid.uuid4(),
    )
    entry = DailyActivityEntry(
        id=uuid.uuid4(),
        daily_card_id=uuid.uuid4(),
        activity_id=activity.id,
        category_activity_config_id=config.id,
        is_filled=filled,
        daily_score=None,
        rule_version_id=None,
        max_score_snapshot=max_score,
    )
    entry.activity = activity
    entry.category_activity_config = config
    entry.values = []

    for order, (key, input_type, is_filled, raw_value) in enumerate(fields, start=1):
        field = ActivityField(
            id=uuid.uuid4(),
            activity_id=activity.id,
            field_key=key,
            label=key,
            input_type=input_type,
            unit_code=None,
            display_order=order,
            required_for_completion=True,
            is_active=True,
            is_archived=False,
        )
        value = DailyActivityValue(
            id=uuid.uuid4(),
            daily_activity_entry_id=entry.id,
            activity_field_id=field.id,
            is_filled=is_filled,
            numeric_value=Decimal("0"),
            time_value=None,
            boolean_value=None,
            text_value=None,
        )
        value.activity_field = field
        if is_filled:
            if input_type in {
                ActivityInputType.NUMBER,
                ActivityInputType.COUNT,
                ActivityInputType.DURATION,
            }:
                value.numeric_value = Decimal(str(raw_value))
            elif input_type == ActivityInputType.TIME:
                value.time_value = raw_value
            elif input_type == ActivityInputType.BOOLEAN:
                value.boolean_value = raw_value
            else:
                value.text_value = raw_value
        entry.values.append(value)

    if rule_type is not None:
        rule = ScoringRule(
            id=uuid.uuid4(),
            organization_id=activity.organization_id,
            activity_id=activity.id,
            name=f"{code} rule",
            rule_type=rule_type,
            is_active=True,
            is_archived=False,
            created_by_id=uuid.uuid4(),
        )
        version = ScoringRuleVersion(
            id=uuid.uuid4(),
            scoring_rule_id=rule.id,
            version_number=1,
            effective_from_week=date(2026, 9, 14),
            status=VersionStatus.ACTIVE,
            max_score=max_score or 0,
            configuration=configuration or {},
            created_by_id=uuid.uuid4(),
        )
        version.scoring_rule = rule
        entry.rule_version = version
        entry.rule_version_id = version.id
        config.scoring_rule_id = rule.id
    return entry


def test_all_seeded_rule_configurations_are_executable() -> None:
    for activity in ACTIVITY_SEEDS:
        if activity.rule is None:
            continue
        validate_rule_configuration(
            activity.rule.rule_type,
            activity.rule.configuration,
            activity.rule.max_score,
        )


def test_boolean_false_is_filled_but_scores_zero() -> None:
    entry = _entry(
        code="MORNING_PROGRAM",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.BOOLEAN,
        configuration={"input_field": "attended", "true_score": 30, "false_score": 0},
        max_score=30,
        fields=[("attended", ActivityInputType.BOOLEAN, True, False)],
    )
    outcome = evaluate_daily_entry(entry)
    assert outcome.score == 0
    assert outcome.details["input_filled"] is True
    assert outcome.details["input_value"] is False


def test_missing_boolean_scores_zero_without_losing_missing_semantics() -> None:
    entry = _entry(
        code="MORNING_CLASS",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.BOOLEAN,
        configuration={"input_field": "attended", "true_score": 30, "false_score": 0},
        max_score=30,
        fields=[("attended", ActivityInputType.BOOLEAN, False, None)],
        filled=False,
    )
    outcome = evaluate_daily_entry(entry)
    assert outcome.score == 0
    assert outcome.details["reason"] == "MISSING_INPUT"


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [(0, 0), (29, 0), (30, 10), (59, 10), (60, 20), (119, 20), (120, 30)],
)
def test_study_threshold_boundaries(minutes: int, expected: int) -> None:
    entry = _entry(
        code="STUDY_PREPARATION",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.THRESHOLD,
        configuration={
            "input_field": "minutes",
            "thresholds": [
                {"operator": ">=", "value": 120, "score": 30},
                {"operator": ">=", "value": 60, "score": 20},
                {"operator": ">=", "value": 30, "score": 10},
            ],
            "otherwise": 0,
        },
        max_score=30,
        fields=[("minutes", ActivityInputType.DURATION, True, minutes)],
    )
    assert evaluate_daily_entry(entry).score == expected


def test_day_rest_exactly_45_minutes_scores_50() -> None:
    entry = _entry(
        code="DAY_REST",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.THRESHOLD,
        configuration={
            "input_field": "minutes",
            "thresholds": [
                {"operator": "<", "value": 30, "score": 70},
                {"operator": "<=", "value": 45, "score": 50},
                {"operator": "<=", "value": 60, "score": 30},
            ],
            "otherwise": 0,
        },
        max_score=70,
        fields=[("minutes", ActivityInputType.DURATION, True, 45)],
    )
    assert evaluate_daily_entry(entry).score == 50


def test_to_bed_exactly_2115_scores_50() -> None:
    entry = _entry(
        code="TO_BED",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.THRESHOLD,
        configuration={
            "input_field": "bedtime",
            "thresholds": [
                {"operator": "<", "value": "21:15", "score": 70},
                {"operator": "<", "value": "21:30", "score": 50},
                {"operator": "<", "value": "21:45", "score": 30},
                {"operator": "<", "value": "22:00", "score": 10},
            ],
            "otherwise": 0,
        },
        max_score=70,
        fields=[("bedtime", ActivityInputType.TIME, True, time(21, 15))],
    )
    assert evaluate_daily_entry(entry).score == 50


def test_wake_up_exactly_0340_scores_50() -> None:
    entry = _entry(
        code="WAKE_UP",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.THRESHOLD,
        configuration={
            "input_field": "wake_up_time",
            "thresholds": [
                {"operator": "<", "value": "03:40", "score": 70},
                {"operator": "<", "value": "03:50", "score": 50},
                {"operator": "<", "value": "04:00", "score": 30},
                {"operator": "<", "value": "04:15", "score": 10},
            ],
            "otherwise": 0,
        },
        max_score=70,
        fields=[("wake_up_time", ActivityInputType.TIME, True, time(3, 40))],
    )
    assert evaluate_daily_entry(entry).score == 50


def _chanting_entry(rounds: int, completion: time | None) -> DailyActivityEntry:
    return _entry(
        code="CHANTING",
        scoring_type=ScoringType.DAILY,
        rule_type=RuleType.THRESHOLD,
        configuration={
            "required_rounds": 16,
            "rounds_field": "rounds_chanted",
            "completion_field": "completion_time",
            "thresholds": [
                {"before": "09:30", "score": 70},
                {"before": "11:00", "score": 50},
                {"before": "12:30", "score": 30},
                {"before": "16:00", "score": 20},
                {"before": "19:00", "score": 10},
            ],
            "otherwise": 0,
        },
        max_score=70,
        fields=[
            ("rounds_chanted", ActivityInputType.COUNT, True, rounds),
            ("completion_time", ActivityInputType.TIME, completion is not None, completion),
        ],
    )


def test_chanting_below_16_scores_zero_without_completion_time() -> None:
    outcome = evaluate_daily_entry(_chanting_entry(12, None))
    assert outcome.score == 0
    assert outcome.details["reason"] == "REQUIRED_ROUNDS_NOT_REACHED"


def test_chanting_16_without_completion_time_scores_zero() -> None:
    outcome = evaluate_daily_entry(_chanting_entry(16, None))
    assert outcome.score == 0
    assert outcome.details["reason"] == "MISSING_COMPLETION_TIME"


def test_chanting_exactly_0930_scores_50_because_before_is_strict() -> None:
    outcome = evaluate_daily_entry(_chanting_entry(16, time(9, 30)))
    assert outcome.score == 50
    assert outcome.details["matched_threshold"]["value"] == "11:00"


def test_chanting_before_0930_scores_70() -> None:
    assert evaluate_daily_entry(_chanting_entry(16, time(9, 29))).score == 70


def test_weekly_aggregated_and_non_scored_do_not_get_daily_marks() -> None:
    weekly = _entry(
        code="BOOK_READING",
        scoring_type=ScoringType.WEEKLY_AGGREGATED,
        rule_type=None,
        configuration=None,
        max_score=None,
        fields=[("minutes", ActivityInputType.DURATION, True, 300)],
    )
    seva = _entry(
        code="SEVA",
        scoring_type=ScoringType.NON_SCORED,
        rule_type=None,
        configuration=None,
        max_score=None,
        fields=[("minutes", ActivityInputType.DURATION, True, 60)],
    )
    assert evaluate_daily_entry(weekly).score is None
    assert evaluate_daily_entry(seva).score is None


def test_system_derived_card_fill_is_only_scored_when_explicitly_allowed() -> None:
    fill = _entry(
        code="FILLING_SADHANA_CARD",
        scoring_type=ScoringType.SYSTEM_DERIVED,
        rule_type=RuleType.SYSTEM_DERIVED,
        configuration={
            "formula": "CARD_COMPLETION_PERCENTAGE",
            "minimum_percentage": 75,
            "score_if_met": 10,
            "otherwise": 0,
            "exclude_self": True,
        },
        max_score=10,
        fields=[],
        counts_toward_card_fill=False,
        system_derived=True,
    )
    countable = [
        _entry(
            code=f"A{i}",
            scoring_type=ScoringType.NON_SCORED,
            rule_type=None,
            configuration=None,
            max_score=None,
            fields=[("minutes", ActivityInputType.DURATION, True, 1)],
            filled=i < 3,
        )
        for i in range(4)
    ]
    assert evaluate_daily_entry(fill, card_entries=[fill, *countable]).score is None
    outcome = evaluate_daily_entry(
        fill,
        card_entries=[fill, *countable],
        allow_system_derived=True,
    )
    assert outcome.score == 10
    assert outcome.details["completed_count"] == 3
    assert outcome.details["countable_count"] == 4
    assert outcome.details["completion_percentage"] == "75.00"


def test_card_fill_below_75_percent_scores_zero() -> None:
    fill = _entry(
        code="FILLING_SADHANA_CARD",
        scoring_type=ScoringType.SYSTEM_DERIVED,
        rule_type=RuleType.SYSTEM_DERIVED,
        configuration={
            "formula": "CARD_COMPLETION_PERCENTAGE",
            "minimum_percentage": 75,
            "score_if_met": 10,
            "otherwise": 0,
            "exclude_self": True,
        },
        max_score=10,
        fields=[],
        counts_toward_card_fill=False,
        system_derived=True,
    )
    countable = [
        _entry(
            code=f"B{i}",
            scoring_type=ScoringType.NON_SCORED,
            rule_type=None,
            configuration=None,
            max_score=None,
            fields=[("minutes", ActivityInputType.DURATION, True, 1)],
            filled=i < 2,
        )
        for i in range(4)
    ]
    outcome = evaluate_daily_entry(
        fill,
        card_entries=[fill, *countable],
        allow_system_derived=True,
    )
    assert outcome.score == 0
    assert outcome.details["completion_percentage"] == "50.00"


def test_rule_validation_rejects_score_above_maximum() -> None:
    with pytest.raises(ScoringConfigurationError):
        validate_rule_configuration(
            RuleType.BOOLEAN,
            {"input_field": "attended", "true_score": 31, "false_score": 0},
            30,
        )


def test_rule_validation_rejects_unsorted_chanting_time_thresholds() -> None:
    with pytest.raises(ScoringConfigurationError):
        validate_rule_configuration(
            RuleType.THRESHOLD,
            {
                "required_rounds": 16,
                "rounds_field": "rounds_chanted",
                "completion_field": "completion_time",
                "thresholds": [
                    {"before": "11:00", "score": 50},
                    {"before": "09:30", "score": 70},
                ],
                "otherwise": 0,
            },
            70,
        )
