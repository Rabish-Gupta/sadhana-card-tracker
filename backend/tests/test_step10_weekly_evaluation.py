from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.enums import ActivityCategory, ScoringType
from app.db.seed_data import ACTIVITY_SEEDS
from app.services.weekly_evaluations import (
    PartialLifecycleWeekError,
    _percentage_weekly_score,
    validate_full_lifecycle_window,
)
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import StandardVersion
from app.core.enums import RuleType, StandardPeriod, VersionStatus


def test_seeded_baseline_weekly_maxima_stay_1750_separately() -> None:
    totals = {ActivityCategory.SADHANA: 0, ActivityCategory.ACADEMIC: 0}
    for activity in ACTIVITY_SEEDS:
        if activity.scoring_type in {ScoringType.DAILY, ScoringType.SYSTEM_DERIVED}:
            assert activity.rule is not None
            totals[activity.category] += activity.rule.max_score * 7
        elif activity.scoring_type == ScoringType.WEEKLY_AGGREGATED:
            assert activity.rule is not None
            totals[activity.category] += activity.rule.max_score
        elif activity.scoring_type == ScoringType.NON_SCORED:
            continue
    assert totals[ActivityCategory.SADHANA] == 1750
    assert totals[ActivityCategory.ACADEMIC] == 1750


def test_partial_lifecycle_approval_midweek_is_not_prorated() -> None:
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    with pytest.raises(PartialLifecycleWeekError):
        validate_full_lifecycle_window(
            approved_at=start + timedelta(days=3),
            lifecycle_events=[],
            start_utc=start,
            next_start_utc=start + timedelta(days=7),
        )


def test_partial_lifecycle_deactivation_midweek_is_not_scored() -> None:
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    with pytest.raises(PartialLifecycleWeekError):
        validate_full_lifecycle_window(
            approved_at=start - timedelta(days=30),
            lifecycle_events=[("ACCOUNT_DEACTIVATED", start + timedelta(days=2))],
            start_utc=start,
            next_start_utc=start + timedelta(days=7),
        )


def test_full_lifecycle_week_is_allowed() -> None:
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    validate_full_lifecycle_window(
        approved_at=start - timedelta(days=30),
        lifecycle_events=[
            ("ACCOUNT_DEACTIVATED", start - timedelta(days=20)),
            ("ACCOUNT_ACTIVATED", start - timedelta(days=10)),
        ],
        start_utc=start,
        next_start_utc=start + timedelta(days=7),
    )


def _percentage_models(max_score: int, target: int):
    rule = ScoringRule(
        organization_id=__import__('uuid').uuid4(),
        activity_id=__import__('uuid').uuid4(),
        name="percentage",
        rule_type=RuleType.PERCENTAGE,
        is_active=True,
        is_archived=False,
        created_by_id=__import__('uuid').uuid4(),
    )
    version = ScoringRuleVersion(
        scoring_rule_id=__import__('uuid').uuid4(),
        version_number=1,
        effective_from_week=__import__('datetime').date(2026, 9, 14),
        status=VersionStatus.ACTIVE,
        max_score=max_score,
        configuration={
            "formula": "STANDARD_PERCENTAGE_X_MAX_SCORE",
            "cap_percentage": 100,
            "rounding": "HALF_UP",
        },
        created_by_id=__import__('uuid').uuid4(),
    )
    version.scoring_rule = rule
    standard = StandardVersion(
        standard_id=__import__('uuid').uuid4(),
        version_number=1,
        effective_from_week=__import__('datetime').date(2026, 9, 14),
        period=StandardPeriod.WEEKLY,
        target_definition={"kind": "DURATION", "value": target, "unit": "MINUTE", "operator": ">="},
        status=VersionStatus.ACTIVE,
        created_by_id=__import__('uuid').uuid4(),
    )
    return version, standard


def test_book_reading_percentage_score_half_up_and_capped() -> None:
    rule, standard = _percentage_models(490, 300)
    score, details = _percentage_weekly_score(
        raw_total=Decimal("150"), rule_version=rule, standard_version=standard
    )
    assert score == 245
    assert details["raw_percentage"] == "50.00"

    score2, details2 = _percentage_weekly_score(
        raw_total=Decimal("450"), rule_version=rule, standard_version=standard
    )
    assert score2 == 490
    assert details2["raw_percentage"] == "150.00"
    assert details2["scoring_percentage"] == "100.00"


def test_personal_hearing_target_gives_full_210() -> None:
    rule, standard = _percentage_models(210, 120)
    score, _ = _percentage_weekly_score(
        raw_total=Decimal("120"), rule_version=rule, standard_version=standard
    )
    assert score == 210


def test_weekly_smoke_reuses_one_asyncio_event_loop() -> None:
    """Guard against reintroducing multiple asyncio.run() calls with the cached async engine."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "scripts" / "weekly_evaluation_smoke_test.py").read_text()
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]

    asyncio_run_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "run"
    ]
    runner_ctor_calls = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
        and node.func.attr == "Runner"
    ]

    assert asyncio_run_calls == []
    assert len(runner_ctor_calls) == 1
    assert "runner.run(prepare_full_week" in source
    assert "runner.run(move_cleanup_after_week" in source
