from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.core.enums import ActivityCategory, ScoringType
from app.services.monthly_reports import (
    _activity_summary,
    _build_report,
    _exact_block,
    _latest_block,
    _score_summary,
    _trend,
)


def _weekly(start: date, *, sadhana=100, academic=200):
    return SimpleNamespace(
        week_start_date=start,
        week_end_date=start + timedelta(days=6),
        sadhana_score=sadhana,
        sadhana_max_score=1750,
        sadhana_percentage=Decimal(str(sadhana / 17.5)).quantize(Decimal("0.01")),
        academic_score=academic,
        academic_max_score=1750,
        academic_percentage=Decimal(str(academic / 17.5)).quantize(Decimal("0.01")),
        activity_results=[],
    )


def test_exact_four_adjacent_complete_weeks_only() -> None:
    start = date(2026, 8, 3)
    weeks = [_weekly(start + timedelta(days=7 * i)) for i in range(4)]
    by_start = {w.week_start_date: w for w in weeks}
    block = _exact_block(by_start, period_start=start, local_today=date(2026, 9, 1))
    assert block == weeks

    del by_start[start + timedelta(days=14)]
    assert _exact_block(by_start, period_start=start, local_today=date(2026, 9, 1)) is None


def test_latest_block_skips_gap_and_finds_latest_valid_run() -> None:
    start = date(2026, 6, 1)
    valid = [_weekly(start + timedelta(days=7 * i)) for i in range(4)]
    later_but_incomplete_run = [_weekly(start + timedelta(days=7 * i)) for i in (5, 6, 8)]
    block = _latest_block(valid + later_but_incomplete_run, local_today=date(2026, 9, 1))
    assert [w.week_start_date for w in block] == [w.week_start_date for w in valid]


def test_current_unfinished_week_cannot_be_in_monthly_report() -> None:
    start = date(2026, 8, 31)
    weeks = [_weekly(start + timedelta(days=7 * i)) for i in range(4)]
    by_start = {w.week_start_date: w for w in weeks}
    assert _exact_block(by_start, period_start=start, local_today=weeks[-1].week_end_date) is None


def test_monthly_score_summary_keeps_sadhana_and_academic_separate() -> None:
    start = date(2026, 7, 6)
    weeks = [_weekly(start + timedelta(days=7 * i), sadhana=1000, academic=1200) for i in range(4)]
    sadhana = _score_summary(weeks, category="SADHANA")
    academic = _score_summary(weeks, category="ACADEMIC")
    assert sadhana.score == 4000
    assert sadhana.maximum_score == 7000
    assert academic.score == 4800
    assert academic.maximum_score == 7000
    assert sadhana.percentage != academic.percentage


def test_trend_is_factual_not_combined_balance_score() -> None:
    trend = _trend([Decimal("50"), Decimal("60"), Decimal("55"), Decimal("70")])
    assert trend.first_percentage == Decimal("50")
    assert trend.last_percentage == Decimal("70")
    assert trend.change_percentage_points == Decimal("20.00")
    assert trend.range_percentage_points == Decimal("20.00")


def test_activity_month_rollup_preserves_non_scored_activity() -> None:
    activity = SimpleNamespace(id=uuid4(), code="SEVA", name="Seva", category=ActivityCategory.ACADEMIC)
    config = SimpleNamespace(scoring_type=ScoringType.NON_SCORED)
    results = []
    start = date(2026, 8, 3)
    for i, raw in enumerate((60, 90, 30, 120)):
        weekly = SimpleNamespace(week_start_date=start + timedelta(days=7 * i), week_end_date=start + timedelta(days=7 * i + 6))
        results.append(
            SimpleNamespace(
                weekly_evaluation=weekly,
                activity_id=activity.id,
                activity=activity,
                category_activity_config=config,
                final_activity_score=None,
                maximum_score=None,
                raw_total=Decimal(raw),
                standard_achievement=Decimal("100"),
                category_activity_config_id=uuid4(),
                rule_version_id=None,
                standard_version_id=None,
                standard_snapshot={"kind": "DURATION", "value": 60},
                calculation_details={
                    "standard": {"period": "DAILY", "achieved_days": 7, "evaluated_days": 7}
                },
            )
        )
    public = _activity_summary(
        results,
        previous_results=None,
        previous_start=None,
        previous_end=None,
    )
    assert public.final_score_total is None
    assert public.maximum_score_total is None
    assert public.raw_total_sum == Decimal("300.00")
    assert public.daily_standard_achieved_days == 28
    assert public.daily_standard_evaluated_days == 28


def test_monthly_routes_are_exposed() -> None:
    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/monthly/latest" in paths
    assert "/api/v1/monthly/{period_start_date}" in paths


def test_four_week_definition_may_cross_calendar_month_boundary() -> None:
    start = date(2026, 8, 17)
    weeks = [_weekly(start + timedelta(days=7 * i)) for i in range(4)]
    block = _exact_block(
        {w.week_start_date: w for w in weeks},
        period_start=start,
        local_today=date(2026, 9, 20),
    )
    assert block is not None
    assert block[0].week_start_date.month == 8
    assert block[-1].week_end_date.month == 9


def test_build_report_uses_real_devotee_category_display_name() -> None:
    """Regression: DevoteeCategory exposes display_name, not name."""
    from app.models.devotee import DevoteeCategory
    from app.models.weekly_evaluation import WeeklyEvaluation

    category = DevoteeCategory(
        organization_id=uuid4(),
        code="ARJUNA",
        display_name="Arjuna",
        academic_year=3,
        stage_order=3,
        is_active=True,
        is_archived=False,
    )
    start = date(2026, 8, 17)
    weeks = []
    for i in range(4):
        week_start = start + timedelta(days=7 * i)
        weekly = WeeklyEvaluation(
            organization_id=uuid4(),
            devotee_profile_id=uuid4(),
            week_start_date=week_start,
            week_end_date=week_start + timedelta(days=6),
            category_snapshot_id=uuid4(),
            timezone_snapshot="Asia/Kolkata",
            sadhana_score=1000 + i * 100,
            sadhana_max_score=1750,
            sadhana_percentage=Decimal("57.14") + Decimal(i),
            academic_score=900 + i * 100,
            academic_max_score=1750,
            academic_percentage=Decimal("51.43") + Decimal(i),
            revision_number=0,
        )
        weekly.category_snapshot = category
        weekly.activity_results = []
        weeks.append(weekly)

    report = _build_report(weeks, previous=None)
    assert report.weeks[0].category_code == "ARJUNA"
    assert report.weeks[0].category_name == "Arjuna"
    assert report.weeks_count == 4
    payload = report.model_dump(mode="json")
    assert payload["weeks"][0]["category_name"] == "Arjuna"


def test_monthly_json_contract_uses_decimal_strings() -> None:
    """FastAPI/Pydantic serializes Decimal report metrics as JSON strings.

    Keep the contract explicit so smoke tests and frontend clients do not accidentally
    treat precise percentage/raw values as JSON numbers.
    """
    from app.schemas.monthly_report import PreviousFourWeekSummaryPublic

    payload = PreviousFourWeekSummaryPublic(
        period_start_date=date(2026, 7, 20),
        period_end_date=date(2026, 8, 16),
        sadhana_score=4000,
        sadhana_max_score=7000,
        sadhana_percentage=Decimal("57.14"),
        academic_score=4200,
        academic_max_score=7000,
        academic_percentage=Decimal("60.00"),
        sadhana_change_percentage_points=Decimal("5.25"),
        academic_change_percentage_points=Decimal("4.75"),
    ).model_dump(mode="json")

    assert payload["sadhana_percentage"] == "57.14"
    assert payload["academic_percentage"] == "60.00"
    assert payload["sadhana_change_percentage_points"] == "5.25"
    assert payload["academic_change_percentage_points"] == "4.75"
