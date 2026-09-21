from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.timezone import organization_local_date
from app.models.devotee import DevoteeProfile
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation
from app.schemas.monthly_report import (
    FourWeekActivityPublic,
    FourWeekActivityWeekPublic,
    FourWeekReportPublic,
    FourWeekScoreSummaryPublic,
    FourWeekTrendPublic,
    FourWeekWeekPublic,
    PreviousFourWeekActivityPublic,
    PreviousFourWeekSummaryPublic,
)


class MonthlyReportError(ValueError):
    pass


class MonthlyReportNotFoundError(MonthlyReportError):
    pass


class MonthlyReportNotReadyError(MonthlyReportError):
    pass


_FOUR_WEEKS = 4
_WEEK = timedelta(days=7)
_PERIOD = timedelta(days=28)

_LOAD_OPTIONS = (
    selectinload(WeeklyEvaluation.category_snapshot),
    selectinload(WeeklyEvaluation.activity_results).selectinload(WeeklyActivityResult.activity),
    selectinload(WeeklyEvaluation.activity_results).selectinload(
        WeeklyActivityResult.category_activity_config
    ),
)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _percentage(score: int | Decimal, maximum: int | Decimal) -> Decimal | None:
    maximum_decimal = Decimal(maximum)
    if maximum_decimal <= 0:
        return None
    return _q2(Decimal(score) / maximum_decimal * Decimal("100"))


def _average(values: Iterable[Decimal]) -> Decimal | None:
    items = list(values)
    if not items:
        return None
    return _q2(sum(items, Decimal("0")) / Decimal(len(items)))


def _trend(percentages: list[Decimal | None]) -> FourWeekTrendPublic:
    available = [value for value in percentages if value is not None]
    if not available:
        return FourWeekTrendPublic()
    first = percentages[0]
    last = percentages[-1]
    change = _q2(last - first) if first is not None and last is not None else None
    minimum = min(available)
    maximum = max(available)
    return FourWeekTrendPublic(
        first_percentage=first,
        last_percentage=last,
        change_percentage_points=change,
        average_percentage=_average(available),
        minimum_percentage=minimum,
        maximum_percentage=maximum,
        range_percentage_points=_q2(maximum - minimum),
    )


async def _profile_and_org(
    session: AsyncSession, *, user: User
) -> tuple[DevoteeProfile, Organization]:
    result = await session.execute(
        select(DevoteeProfile, Organization)
        .join(User, User.id == DevoteeProfile.user_id)
        .join(Organization, Organization.id == User.organization_id)
        .where(DevoteeProfile.user_id == user.id)
    )
    row = result.one_or_none()
    if row is None:
        raise MonthlyReportNotFoundError("Devotee profile or organization not found")
    return row[0], row[1]


async def _load_all_weekly(
    session: AsyncSession, *, profile_id
) -> list[WeeklyEvaluation]:
    result = await session.execute(
        select(WeeklyEvaluation)
        .options(*_LOAD_OPTIONS)
        .where(WeeklyEvaluation.devotee_profile_id == profile_id)
        .order_by(WeeklyEvaluation.week_start_date.asc())
    )
    return list(result.scalars().unique().all())


def _is_complete_evaluation(weekly: WeeklyEvaluation, *, local_today: date) -> bool:
    return (
        weekly.week_end_date == weekly.week_start_date + timedelta(days=6)
        and weekly.week_end_date < local_today
    )


def _exact_block(
    by_start: dict[date, WeeklyEvaluation],
    *, period_start: date,
    local_today: date,
) -> list[WeeklyEvaluation] | None:
    expected = [period_start + _WEEK * offset for offset in range(_FOUR_WEEKS)]
    block: list[WeeklyEvaluation] = []
    for week_start in expected:
        weekly = by_start.get(week_start)
        if weekly is None or not _is_complete_evaluation(weekly, local_today=local_today):
            return None
        block.append(weekly)
    return block


def _latest_block(
    evaluations: list[WeeklyEvaluation], *, local_today: date
) -> list[WeeklyEvaluation] | None:
    by_start = {weekly.week_start_date: weekly for weekly in evaluations}
    for candidate_end in sorted(by_start, reverse=True):
        candidate_start = candidate_end - _WEEK * 3
        block = _exact_block(by_start, period_start=candidate_start, local_today=local_today)
        if block is not None:
            return block
    return None


def _score_summary(
    evaluations: list[WeeklyEvaluation], *, category: str
) -> FourWeekScoreSummaryPublic:
    if category == "SADHANA":
        scores = [weekly.sadhana_score for weekly in evaluations]
        maxima = [weekly.sadhana_max_score for weekly in evaluations]
        percentages = [weekly.sadhana_percentage for weekly in evaluations]
    else:
        scores = [weekly.academic_score for weekly in evaluations]
        maxima = [weekly.academic_max_score for weekly in evaluations]
        percentages = [weekly.academic_percentage for weekly in evaluations]
    score_total = sum(scores)
    maximum_total = sum(maxima)
    return FourWeekScoreSummaryPublic(
        score=score_total,
        maximum_score=maximum_total,
        percentage=_percentage(score_total, maximum_total),
        trend=_trend(percentages),
    )


def _activity_map(evaluations: list[WeeklyEvaluation]) -> dict[object, list[WeeklyActivityResult]]:
    result: dict[object, list[WeeklyActivityResult]] = defaultdict(list)
    for weekly in evaluations:
        for activity_result in weekly.activity_results:
            # Make the parent explicit so report construction never relies on an async lazy-load.
            activity_result.weekly_evaluation = weekly
            result[activity_result.activity_id].append(activity_result)
    return result


def _standard_rollup(
    results: list[WeeklyActivityResult],
) -> tuple[list[str], Decimal | None, int | None, int | None, int | None, int | None]:
    achievements = [r.standard_achievement for r in results if r.standard_achievement is not None]
    periods: list[str] = []
    daily_achieved = 0
    daily_evaluated = 0
    weekly_met = 0
    weekly_evaluated = 0

    for result in results:
        standard = (result.calculation_details or {}).get("standard")
        if not standard:
            continue
        period = str(standard.get("period", ""))
        if period and period not in periods:
            periods.append(period)
        if period == "DAILY":
            daily_achieved += int(standard.get("achieved_days", 0))
            daily_evaluated += int(standard.get("evaluated_days", 0))
        elif period == "WEEKLY":
            weekly_evaluated += 1
            if bool(standard.get("met", False)):
                weekly_met += 1

    return (
        periods,
        _average([Decimal(value) for value in achievements]),
        daily_achieved if daily_evaluated else None,
        daily_evaluated if daily_evaluated else None,
        weekly_met if weekly_evaluated else None,
        weekly_evaluated if weekly_evaluated else None,
    )


def _activity_summary(
    results: list[WeeklyActivityResult],
    *, previous_results: list[WeeklyActivityResult] | None,
    previous_start: date | None,
    previous_end: date | None,
) -> FourWeekActivityPublic:
    ordered = sorted(results, key=lambda r: r.weekly_evaluation.week_start_date)
    first = ordered[0]
    scores = [r.final_activity_score for r in ordered]
    maxima = [r.maximum_score for r in ordered]
    raw = [r.raw_total for r in ordered]

    scored_pairs = [(score, maximum) for score, maximum in zip(scores, maxima) if score is not None and maximum is not None]
    final_score_total = sum(score for score, _ in scored_pairs) if scored_pairs else None
    maximum_score_total = sum(maximum for _, maximum in scored_pairs) if scored_pairs else None
    score_percentage = (
        _percentage(final_score_total, maximum_score_total)
        if final_score_total is not None and maximum_score_total is not None
        else None
    )
    raw_values = [Decimal(value) for value in raw if value is not None]
    raw_sum = _q2(sum(raw_values, Decimal("0"))) if raw_values else None

    periods, achievement_average, daily_achieved, daily_evaluated, weekly_met, weekly_evaluated = _standard_rollup(ordered)

    previous_public = None
    if previous_results and previous_start is not None and previous_end is not None:
        previous_ordered = sorted(
            previous_results, key=lambda r: r.weekly_evaluation.week_start_date
        )
        prev_pairs = [
            (r.final_activity_score, r.maximum_score)
            for r in previous_ordered
            if r.final_activity_score is not None and r.maximum_score is not None
        ]
        prev_score = sum(score for score, _ in prev_pairs) if prev_pairs else None
        prev_max = sum(maximum for _, maximum in prev_pairs) if prev_pairs else None
        prev_raw_values = [Decimal(r.raw_total) for r in previous_ordered if r.raw_total is not None]
        _, prev_standard_avg, *_ = _standard_rollup(previous_ordered)
        previous_public = PreviousFourWeekActivityPublic(
            period_start_date=previous_start,
            period_end_date=previous_end,
            final_score_total=prev_score,
            maximum_score_total=prev_max,
            score_percentage=(
                _percentage(prev_score, prev_max)
                if prev_score is not None and prev_max is not None
                else None
            ),
            raw_total_sum=(
                _q2(sum(prev_raw_values, Decimal("0"))) if prev_raw_values else None
            ),
            standard_achievement_average=prev_standard_avg,
        )

    scoring_types = []
    for result in ordered:
        scoring_type = result.category_activity_config.scoring_type
        if scoring_type not in scoring_types:
            scoring_types.append(scoring_type)

    return FourWeekActivityPublic(
        activity_id=first.activity_id,
        code=first.activity.code,
        name=first.activity.name,
        category=first.activity.category,
        scoring_types_seen=scoring_types,
        final_score_total=final_score_total,
        maximum_score_total=maximum_score_total,
        score_percentage=score_percentage,
        raw_total_sum=raw_sum,
        weekly_raw_totals=raw,
        weekly_final_scores=scores,
        weekly_maximum_scores=maxima,
        weekly_results=[
            FourWeekActivityWeekPublic(
                week_start_date=result.weekly_evaluation.week_start_date,
                week_end_date=result.weekly_evaluation.week_end_date,
                raw_total=result.raw_total,
                final_activity_score=result.final_activity_score,
                maximum_score=result.maximum_score,
                standard_achievement=result.standard_achievement,
                category_activity_config_id=result.category_activity_config_id,
                rule_version_id=result.rule_version_id,
                standard_version_id=result.standard_version_id,
                standard_snapshot=result.standard_snapshot,
            )
            for result in ordered
        ],
        standard_achievement_average=achievement_average,
        standard_periods_seen=periods,
        daily_standard_achieved_days=daily_achieved,
        daily_standard_evaluated_days=daily_evaluated,
        weekly_standard_met_weeks=weekly_met,
        weekly_standard_evaluated_weeks=weekly_evaluated,
        previous_period=previous_public,
    )


def _previous_summary(
    current_sadhana: FourWeekScoreSummaryPublic,
    current_academic: FourWeekScoreSummaryPublic,
    previous: list[WeeklyEvaluation] | None,
) -> PreviousFourWeekSummaryPublic | None:
    if previous is None:
        return None
    sadhana = _score_summary(previous, category="SADHANA")
    academic = _score_summary(previous, category="ACADEMIC")
    return PreviousFourWeekSummaryPublic(
        period_start_date=previous[0].week_start_date,
        period_end_date=previous[-1].week_end_date,
        sadhana_score=sadhana.score,
        sadhana_max_score=sadhana.maximum_score,
        sadhana_percentage=sadhana.percentage,
        academic_score=academic.score,
        academic_max_score=academic.maximum_score,
        academic_percentage=academic.percentage,
        sadhana_change_percentage_points=(
            _q2(current_sadhana.percentage - sadhana.percentage)
            if current_sadhana.percentage is not None and sadhana.percentage is not None
            else None
        ),
        academic_change_percentage_points=(
            _q2(current_academic.percentage - academic.percentage)
            if current_academic.percentage is not None and academic.percentage is not None
            else None
        ),
    )


def _observations(
    *,
    sadhana: FourWeekScoreSummaryPublic,
    academic: FourWeekScoreSummaryPublic,
    previous: PreviousFourWeekSummaryPublic | None,
    activities: list[FourWeekActivityPublic],
) -> list[str]:
    observations: list[str] = []
    if previous is not None:
        if previous.sadhana_change_percentage_points is not None:
            observations.append(
                f"Sadhana percentage changed by {previous.sadhana_change_percentage_points:+.2f} percentage points compared with the previous four-week period."
            )
        if previous.academic_change_percentage_points is not None:
            observations.append(
                f"Academic percentage changed by {previous.academic_change_percentage_points:+.2f} percentage points compared with the previous four-week period."
            )
    else:
        observations.append("No immediately preceding four adjacent complete weeks are available for comparison.")

    if sadhana.trend.range_percentage_points is not None:
        observations.append(
            f"Sadhana weekly percentage range across this period was {sadhana.trend.range_percentage_points:.2f} points."
        )
    if academic.trend.range_percentage_points is not None:
        observations.append(
            f"Academic weekly percentage range across this period was {academic.trend.range_percentage_points:.2f} points."
        )

    for activity in activities:
        if (
            activity.weekly_standard_evaluated_weeks
            and activity.weekly_standard_met_weeks is not None
        ):
            observations.append(
                f"{activity.name}: weekly standard met in {activity.weekly_standard_met_weeks}/{activity.weekly_standard_evaluated_weeks} evaluated weeks."
            )
        elif (
            activity.daily_standard_evaluated_days
            and activity.daily_standard_achieved_days is not None
        ):
            observations.append(
                f"{activity.name}: daily standard achieved on {activity.daily_standard_achieved_days}/{activity.daily_standard_evaluated_days} evaluated days."
            )
        if len(observations) >= 8:
            break
    return observations


def _build_report(
    current: list[WeeklyEvaluation],
    *,
    previous: list[WeeklyEvaluation] | None,
) -> FourWeekReportPublic:
    sadhana = _score_summary(current, category="SADHANA")
    academic = _score_summary(current, category="ACADEMIC")
    previous_public = _previous_summary(sadhana, academic, previous)

    previous_map = _activity_map(previous) if previous else {}
    current_map = _activity_map(current)
    previous_start = previous[0].week_start_date if previous else None
    previous_end = previous[-1].week_end_date if previous else None

    activities = [
        _activity_summary(
            results,
            previous_results=previous_map.get(activity_id),
            previous_start=previous_start,
            previous_end=previous_end,
        )
        for activity_id, results in current_map.items()
    ]
    activities.sort(key=lambda item: (item.category.value, item.name.lower()))

    weeks = [
        FourWeekWeekPublic(
            week_start_date=weekly.week_start_date,
            week_end_date=weekly.week_end_date,
            category_code=weekly.category_snapshot.code,
            category_name=weekly.category_snapshot.display_name,
            sadhana_score=weekly.sadhana_score,
            sadhana_max_score=weekly.sadhana_max_score,
            sadhana_percentage=weekly.sadhana_percentage,
            academic_score=weekly.academic_score,
            academic_max_score=weekly.academic_max_score,
            academic_percentage=weekly.academic_percentage,
        )
        for weekly in current
    ]

    return FourWeekReportPublic(
        period_start_date=current[0].week_start_date,
        period_end_date=current[-1].week_end_date,
        weeks_count=4,
        weeks=weeks,
        sadhana=sadhana,
        academic=academic,
        activities=activities,
        previous_period=previous_public,
        observations=_observations(
            sadhana=sadhana,
            academic=academic,
            previous=previous_public,
            activities=activities,
        ),
        metadata={
            "period_definition": "Exactly four adjacent completed WeeklyEvaluation records; not a calendar month.",
            "combined_balance_score": False,
            "spiritual_advancement_measurement": False,
        },
    )


async def get_four_week_report_public(
    session: AsyncSession,
    *,
    user: User,
    period_start: date,
) -> FourWeekReportPublic:
    profile, organization = await _profile_and_org(session, user=user)
    evaluations = await _load_all_weekly(session, profile_id=profile.id)
    by_start = {weekly.week_start_date: weekly for weekly in evaluations}
    local_today = organization_local_date(organization.timezone)
    current = _exact_block(by_start, period_start=period_start, local_today=local_today)
    if current is None:
        if period_start not in by_start:
            raise MonthlyReportNotFoundError(
                "No Weekly Evaluation exists for the requested four-week period start"
            )
        raise MonthlyReportNotReadyError(
            "Monthly report requires four adjacent complete Weekly Evaluations"
        )

    previous_start = period_start - _PERIOD
    previous = _exact_block(by_start, period_start=previous_start, local_today=local_today)
    return _build_report(current, previous=previous)


async def get_latest_four_week_report_public(
    session: AsyncSession,
    *,
    user: User,
) -> FourWeekReportPublic:
    profile, organization = await _profile_and_org(session, user=user)
    evaluations = await _load_all_weekly(session, profile_id=profile.id)
    local_today = organization_local_date(organization.timezone)
    current = _latest_block(evaluations, local_today=local_today)
    if current is None:
        raise MonthlyReportNotReadyError(
            "No set of four adjacent complete Weekly Evaluations is available yet"
        )
    by_start = {weekly.week_start_date: weekly for weekly in evaluations}
    previous_start = current[0].week_start_date - _PERIOD
    previous = _exact_block(by_start, period_start=previous_start, local_today=local_today)
    return _build_report(current, previous=previous)
