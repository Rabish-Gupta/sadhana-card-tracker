from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ActivityCategory,
    ActivityInputType,
    AggregationMethod,
    CardStatus,
    RuleType,
    ScoringType,
    StandardPeriod,
    VersionStatus,
)
from app.core.timezone import get_week_bounds, organization_local_date, utc_now
from app.models.activity import Activity
from app.models.audit import AuditLog
from app.models.daily_card import DailyActivityEntry, DailyActivityValue, DailyCard
from app.models.devotee import DevoteeCategory, DevoteeProfile
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import Standard, StandardVersion
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation
from app.schemas.weekly_evaluation import (
    PreviousWeekActivityPublic,
    PreviousWeekEvaluationPublic,
    WeeklyActivityResultPublic,
    WeeklyEvaluationPublic,
)
from app.services.daily_cards import materialize_and_finalize_for_scheduler


class WeeklyEvaluationError(ValueError):
    pass


class WeeklyEvaluationNotFoundError(WeeklyEvaluationError):
    pass


class WeeklyEvaluationNotReadyError(WeeklyEvaluationError):
    pass


class PartialLifecycleWeekError(WeeklyEvaluationError):
    """The approved policy is to retain raw cards but not create an official weekly score."""


class WeeklyEvaluationConfigurationError(WeeklyEvaluationError):
    pass


_WEEKLY_LOAD_OPTIONS = (
    selectinload(WeeklyEvaluation.category_snapshot),
    selectinload(WeeklyEvaluation.activity_results).selectinload(WeeklyActivityResult.activity),
    selectinload(WeeklyEvaluation.activity_results).selectinload(
        WeeklyActivityResult.category_activity_config
    ),
    selectinload(WeeklyEvaluation.activity_results)
    .selectinload(WeeklyActivityResult.rule_version)
    .selectinload(ScoringRuleVersion.scoring_rule),
    selectinload(WeeklyEvaluation.activity_results).selectinload(
        WeeklyActivityResult.standard_version
    ),
)

_CARD_WEEK_OPTIONS = (
    selectinload(DailyCard.activity_entries).selectinload(DailyActivityEntry.activity),
    selectinload(DailyCard.activity_entries).selectinload(
        DailyActivityEntry.category_activity_config
    ),
    selectinload(DailyCard.activity_entries)
    .selectinload(DailyActivityEntry.rule_version)
    .selectinload(ScoringRuleVersion.scoring_rule),
    selectinload(DailyCard.activity_entries)
    .selectinload(DailyActivityEntry.values)
    .selectinload(DailyActivityValue.activity_field),
)


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _percentage(numerator: Decimal | int, denominator: Decimal | int) -> Decimal | None:
    den = Decimal(str(denominator))
    if den == 0:
        return None
    return _q2(Decimal(str(numerator)) / den * Decimal("100"))


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "=":
        return actual == expected
    if operator == ">=":
        return actual >= expected
    if operator == ">":
        return actual > expected
    if operator == "<=":
        return actual <= expected
    if operator == "<":
        return actual < expected
    raise WeeklyEvaluationConfigurationError(f"Unsupported standard operator: {operator}")


def _parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    try:
        return time.fromisoformat(str(value))
    except ValueError as exc:
        raise WeeklyEvaluationConfigurationError(
            f"Invalid TIME standard value: {value}"
        ) from exc


def _aggregate_decimal(values: list[Decimal], method: AggregationMethod) -> Decimal:
    if not values:
        return Decimal("0")
    if method == AggregationMethod.SUM:
        return sum(values, Decimal("0"))
    if method == AggregationMethod.AVERAGE:
        return sum(values, Decimal("0")) / Decimal(len(values))
    if method == AggregationMethod.COUNT:
        return Decimal(len(values))
    if method == AggregationMethod.MIN:
        return min(values)
    if method == AggregationMethod.MAX:
        return max(values)
    raise WeeklyEvaluationConfigurationError(f"Unsupported aggregation method: {method}")


def _aggregate_scores(values: list[int], method: AggregationMethod) -> int:
    decimals = [Decimal(value) for value in values]
    return _round_int(_aggregate_decimal(decimals, method))


def _local_midnight_utc(day: date, timezone_name: str) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(timezone_name)).astimezone(timezone.utc)


def _numeric_raw_for_entry(entry: DailyActivityEntry) -> tuple[str | None, Decimal | None, bool]:
    """Return an unambiguous numeric raw field for weekly raw analytics.

    A configured weekly activity may later contain multiple fields.  In that case an
    executable rule should name ``input_field``.  Baseline Book Reading/Personal Hearing
    each have one DURATION field, while Chanting has one numeric rounds field plus TIME.
    """

    configured_key = None
    if entry.rule_version is not None:
        configured_key = entry.rule_version.configuration.get("input_field")

    candidates: list[DailyActivityValue] = []
    for value in entry.values:
        if value.activity_field.input_type in {
            ActivityInputType.NUMBER,
            ActivityInputType.COUNT,
            ActivityInputType.DURATION,
        }:
            if configured_key and value.activity_field.field_key != configured_key:
                continue
            candidates.append(value)

    if not candidates:
        return None, None, False
    if len(candidates) > 1:
        raise WeeklyEvaluationConfigurationError(
            f"{entry.activity.code} has multiple numeric raw fields; weekly aggregation requires input_field"
        )
    value = candidates[0]
    return value.activity_field.field_key, value.numeric_value, value.is_filled


def _standard_actual(entry: DailyActivityEntry, definition: dict[str, Any]) -> tuple[Any | None, bool]:
    kind = str(definition.get("kind", "")).upper()

    # The filling-card standard is factual system output rather than a user field.
    if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
        if kind != "BOOLEAN":
            raise WeeklyEvaluationConfigurationError(
                "SYSTEM_DERIVED daily standards must use BOOLEAN targets"
            )
        details = entry.score_details or {}
        return bool(details.get("met", False)), True

    wanted_types: set[ActivityInputType]
    if kind == "BOOLEAN":
        wanted_types = {ActivityInputType.BOOLEAN}
    elif kind == "TIME":
        wanted_types = {ActivityInputType.TIME}
    elif kind == "COUNT":
        wanted_types = {ActivityInputType.COUNT}
    elif kind == "DURATION":
        wanted_types = {ActivityInputType.DURATION}
    elif kind == "NUMBER":
        wanted_types = {ActivityInputType.NUMBER}
    else:
        raise WeeklyEvaluationConfigurationError(f"Unsupported standard kind: {kind}")

    matches = [value for value in entry.values if value.activity_field.input_type in wanted_types]
    field_key = definition.get("field_key")
    if field_key:
        matches = [value for value in matches if value.activity_field.field_key == field_key]
    if len(matches) != 1:
        raise WeeklyEvaluationConfigurationError(
            f"{entry.activity.code} standard target does not resolve to exactly one raw field"
        )

    value = matches[0]
    if not value.is_filled:
        return None, False
    if kind == "BOOLEAN":
        return value.boolean_value, True
    if kind == "TIME":
        return value.time_value, True
    return value.numeric_value, True


def _daily_standard_met(entry: DailyActivityEntry, definition: dict[str, Any]) -> bool:
    actual, filled = _standard_actual(entry, definition)
    if not filled:
        return False
    kind = str(definition.get("kind", "")).upper()
    expected = definition.get("value")
    operator = str(definition.get("operator", "="))
    if kind == "TIME":
        expected = _parse_time(expected)
    elif kind in {"COUNT", "DURATION", "NUMBER"}:
        expected = Decimal(str(expected))
    elif kind == "BOOLEAN":
        expected = bool(expected)
    return _compare(actual, operator, expected)


def _weekly_standard_metrics(
    *,
    entries: list[DailyActivityEntry],
    raw_total: Decimal | None,
    standard_version: StandardVersion | None,
) -> tuple[Decimal | None, dict[str, Any] | None]:
    if standard_version is None:
        return None, None

    definition = standard_version.target_definition
    if standard_version.period == StandardPeriod.DAILY:
        achieved = sum(1 for entry in entries if _daily_standard_met(entry, definition))
        evaluated = len(entries)
        achievement = _percentage(achieved, evaluated)
        return achievement, {
            "period": "DAILY",
            "achieved_days": achieved,
            "evaluated_days": evaluated,
            "met_all_days": achieved == evaluated,
        }

    if standard_version.period != StandardPeriod.WEEKLY:
        raise WeeklyEvaluationConfigurationError(
            f"Unsupported standard period: {standard_version.period}"
        )
    if raw_total is None:
        raise WeeklyEvaluationConfigurationError(
            "Weekly standard requires a numeric weekly raw aggregate"
        )

    target = Decimal(str(definition.get("value")))
    operator = str(definition.get("operator", ">="))
    achievement = _percentage(raw_total, target) if target != 0 else None
    return achievement, {
        "period": "WEEKLY",
        "actual": str(raw_total),
        "target": str(target),
        "operator": operator,
        "met": _compare(raw_total, operator, target),
    }


def _percentage_weekly_score(
    *, raw_total: Decimal, rule_version: ScoringRuleVersion, standard_version: StandardVersion
) -> tuple[int, dict[str, Any]]:
    config = rule_version.configuration
    if config.get("formula") != "STANDARD_PERCENTAGE_X_MAX_SCORE":
        raise WeeklyEvaluationConfigurationError(
            "Unsupported percentage weekly scoring formula"
        )
    target = Decimal(str(standard_version.target_definition.get("value")))
    if target <= 0:
        raise WeeklyEvaluationConfigurationError("Weekly percentage target must be positive")
    raw_percentage = raw_total / target * Decimal("100")
    cap = Decimal(str(config.get("cap_percentage", 100)))
    scoring_percentage = min(raw_percentage, cap)
    score = _round_int(scoring_percentage / Decimal("100") * Decimal(rule_version.max_score))
    return score, {
        "formula": "STANDARD_PERCENTAGE_X_MAX_SCORE",
        "actual": str(raw_total),
        "target": str(target),
        "raw_percentage": str(_q2(raw_percentage)),
        "scoring_percentage": str(_q2(scoring_percentage)),
        "rounding": str(config.get("rounding", "HALF_UP")),
    }


async def _load_profile_and_org(
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
        raise WeeklyEvaluationNotFoundError("Devotee profile or organization not found")
    return row[0], row[1]


async def _setting_for_week(
    session: AsyncSession, *, organization_id: uuid.UUID, week_start: date
) -> OrganizationSettingVersion:
    result = await session.execute(
        select(OrganizationSettingVersion)
        .where(
            OrganizationSettingVersion.organization_id == organization_id,
            OrganizationSettingVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
            OrganizationSettingVersion.effective_from_week <= week_start,
        )
        .order_by(OrganizationSettingVersion.effective_from_week.desc())
        .limit(1)
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        raise WeeklyEvaluationConfigurationError(
            "No historical organization settings exist for this week"
        )
    canonical_start, _ = get_week_bounds(week_start, setting.week_start_day)
    # A version is activated on the prior/current week boundary.  If week_start_day itself
    # changes, its first effective week may not be canonical under the *new* numbering, so
    # explicitly allow the version's own effective boundary.
    if week_start != canonical_start and week_start != setting.effective_from_week:
        raise WeeklyEvaluationConfigurationError(
            "Requested date is not an organization week boundary"
        )
    return setting


def validate_full_lifecycle_window(
    *,
    approved_at: datetime | None,
    lifecycle_events: Iterable[tuple[str, datetime]],
    start_utc: datetime,
    next_start_utc: datetime,
) -> None:
    """Pure policy-A validator used by the DB service and unit tests.

    An official week exists only when the account was continuously active for the full
    half-open interval ``[week_start midnight, next_week_start midnight)``.  No targets
    or maxima are prorated for approval/reactivation/deactivation inside that interval.
    """

    if approved_at is None or approved_at > start_utc:
        raise PartialLifecycleWeekError(
            "Partial lifecycle week: account was not active from the beginning of the week"
        )

    events = sorted(lifecycle_events, key=lambda item: item[1])
    active_at_start = True
    for action, occurred_at in events:
        if occurred_at >= start_utc:
            break
        if action == "ACCOUNT_DEACTIVATED":
            active_at_start = False
        elif action == "ACCOUNT_ACTIVATED":
            active_at_start = True
    if not active_at_start:
        raise PartialLifecycleWeekError(
            "Partial lifecycle week: account was inactive at the beginning of the week"
        )

    if any(
        start_utc <= occurred_at < next_start_utc
        for action, occurred_at in events
        if action in {"ACCOUNT_DEACTIVATED", "ACCOUNT_ACTIVATED"}
    ):
        raise PartialLifecycleWeekError(
            "Partial lifecycle week: account activation state changed during the week"
        )


async def _assert_full_lifecycle_week(
    session: AsyncSession,
    *,
    user: User,
    week_start: date,
    timezone_name: str,
) -> None:
    """Enforce approved policy A: only continuously-active full lifecycle weeks score."""

    next_week_start = week_start + timedelta(days=7)
    start_utc = _local_midnight_utc(week_start, timezone_name)
    next_start_utc = _local_midnight_utc(next_week_start, timezone_name)

    actions = {"ACCOUNT_DEACTIVATED", "ACCOUNT_ACTIVATED"}
    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.organization_id == user.organization_id,
            AuditLog.entity_type == "USER",
            AuditLog.entity_id == user.id,
            AuditLog.action.in_(actions),
            AuditLog.created_at < next_start_utc,
        )
        .order_by(AuditLog.created_at)
    )
    events = list(result.scalars().all())
    validate_full_lifecycle_window(
        approved_at=user.approved_at,
        lifecycle_events=[(event.action, event.created_at) for event in events],
        start_utc=start_utc,
        next_start_utc=next_start_utc,
    )


async def _resolve_standard_version(
    session: AsyncSession, *, standard_id: uuid.UUID | None, week_start: date
) -> StandardVersion | None:
    if standard_id is None:
        return None
    result = await session.execute(
        select(StandardVersion)
        .where(
            StandardVersion.standard_id == standard_id,
            StandardVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
            StandardVersion.effective_from_week <= week_start,
        )
        .order_by(StandardVersion.effective_from_week.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise WeeklyEvaluationConfigurationError("No historical standard version exists for week")
    return version


async def _resolve_weekly_rule_version(
    session: AsyncSession, *, rule_id: uuid.UUID | None, week_start: date
) -> ScoringRuleVersion | None:
    if rule_id is None:
        return None
    result = await session.execute(
        select(ScoringRuleVersion)
        .where(
            ScoringRuleVersion.scoring_rule_id == rule_id,
            ScoringRuleVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
            ScoringRuleVersion.effective_from_week <= week_start,
        )
        .options(selectinload(ScoringRuleVersion.scoring_rule))
        .order_by(ScoringRuleVersion.effective_from_week.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise WeeklyEvaluationConfigurationError("No historical scoring-rule version exists for week")
    return version


async def _load_weekly_evaluation(
    session: AsyncSession, *, profile_id: uuid.UUID, week_start: date
) -> WeeklyEvaluation | None:
    result = await session.execute(
        select(WeeklyEvaluation)
        .where(
            WeeklyEvaluation.devotee_profile_id == profile_id,
            WeeklyEvaluation.week_start_date == week_start,
        )
        .options(*_WEEKLY_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def _load_week_cards(
    session: AsyncSession, *, profile_id: uuid.UUID, week_start: date, week_end: date
) -> list[DailyCard]:
    result = await session.execute(
        select(DailyCard)
        .where(
            DailyCard.devotee_profile_id == profile_id,
            DailyCard.card_date >= week_start,
            DailyCard.card_date <= week_end,
        )
        .options(*_CARD_WEEK_OPTIONS)
        .order_by(DailyCard.card_date)
    )
    return list(result.scalars().all())


async def _ensure_finalized_week_cards(
    session: AsyncSession,
    *,
    user: User,
    profile: DevoteeProfile,
    week_start: date,
    week_end: date,
    now_utc: datetime,
) -> list[DailyCard]:
    for offset in range(7):
        card_date = week_start + timedelta(days=offset)
        await materialize_and_finalize_for_scheduler(
            session, user=user, target_date=card_date, now_utc=now_utc
        )
    cards = await _load_week_cards(
        session, profile_id=profile.id, week_start=week_start, week_end=week_end
    )
    if len(cards) != 7 or any(card.status != CardStatus.FINALIZED for card in cards):
        raise WeeklyEvaluationNotReadyError(
            "All seven daily cards must be finalized before weekly evaluation"
        )
    return cards


def _validate_week_snapshots(cards: list[DailyCard]) -> tuple[uuid.UUID, str]:
    category_ids = {card.category_snapshot_id for card in cards}
    if len(category_ids) != 1:
        raise WeeklyEvaluationConfigurationError(
            "A weekly evaluation cannot cross a devotee category boundary"
        )
    timezones = {card.timezone_snapshot for card in cards}
    if len(timezones) != 1:
        raise WeeklyEvaluationConfigurationError(
            "A weekly evaluation cannot mix daily-card timezone snapshots"
        )
    return next(iter(category_ids)), next(iter(timezones))


def _entries_by_activity(cards: list[DailyCard]) -> dict[uuid.UUID, list[DailyActivityEntry]]:
    grouped_with_dates: dict[uuid.UUID, list[tuple[date, DailyActivityEntry]]] = defaultdict(list)
    for card in cards:
        for entry in card.activity_entries:
            grouped_with_dates[entry.activity_id].append((card.card_date, entry))

    grouped: dict[uuid.UUID, list[DailyActivityEntry]] = {}
    for activity_id, dated_entries in grouped_with_dates.items():
        dated_entries.sort(key=lambda item: item[0])
        entries = [entry for _, entry in dated_entries]
        if len(entries) != 7:
            raise WeeklyEvaluationConfigurationError(
                f"Activity {activity_id} is not represented on all seven daily cards"
            )
        config_ids = {entry.category_activity_config_id for entry in entries}
        if len(config_ids) != 1:
            raise WeeklyEvaluationConfigurationError(
                "Category/activity configuration changed inside a week"
            )
        grouped[activity_id] = entries
    return grouped


async def _build_activity_result(
    session: AsyncSession,
    *,
    weekly_evaluation: WeeklyEvaluation,
    entries: list[DailyActivityEntry],
    week_start: date,
    historical_snapshot: WeeklyActivityResult | None = None,
) -> WeeklyActivityResult:
    first = entries[0]
    config = first.category_activity_config

    if historical_snapshot is not None:
        if historical_snapshot.activity_id != first.activity_id:
            raise WeeklyEvaluationConfigurationError(
                "Historical weekly result does not match the activity being recalculated"
            )
        if historical_snapshot.category_activity_config_id != config.id:
            raise WeeklyEvaluationConfigurationError(
                "Historical correction cannot replace the stored category/activity config"
            )
        if historical_snapshot.aggregation_method is None:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} historical weekly result has no aggregation method"
            )
        method = AggregationMethod(historical_snapshot.aggregation_method)
        standard_version = historical_snapshot.standard_version
        if (
            historical_snapshot.standard_version_id is not None
            and standard_version is None
        ):
            raise WeeklyEvaluationConfigurationError(
                "Stored historical standard version could not be loaded"
            )
    else:
        method = config.weekly_aggregation
        if method is None:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} has no weekly aggregation method"
            )
        standard_version = await _resolve_standard_version(
            session, standard_id=config.standard_id, week_start=week_start
        )

    raw_field_keys: set[str] = set()
    raw_values: list[Decimal] = []
    raw_fill_flags: list[bool] = []
    for entry in entries:
        key, value, filled = _numeric_raw_for_entry(entry)
        if key is not None and value is not None:
            raw_field_keys.add(key)
            raw_values.append(value)
            raw_fill_flags.append(filled)

    raw_total: Decimal | None = None
    if raw_values:
        if len(raw_values) != 7:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} numeric raw field is inconsistent across the week"
            )
        raw_total = _q2(_aggregate_decimal(raw_values, method))

    standard_achievement, standard_details = _weekly_standard_metrics(
        entries=entries, raw_total=raw_total, standard_version=standard_version
    )

    daily_score_total: int | None = None
    final_score: int | None = None
    maximum_score: int | None = None
    rule_version: ScoringRuleVersion | None = None
    scoring_details: dict[str, Any] | None = None

    if config.scoring_type in {ScoringType.DAILY, ScoringType.SYSTEM_DERIVED}:
        scores = [entry.daily_score for entry in entries]
        max_scores = [entry.max_score_snapshot for entry in entries]
        if any(score is None for score in scores) or any(value is None for value in max_scores):
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} has an unscored finalized daily entry"
            )
        typed_scores = [int(score) for score in scores if score is not None]
        typed_max = [int(value) for value in max_scores if value is not None]
        daily_score_total = sum(typed_scores)
        final_score = _aggregate_scores(typed_scores, method)
        maximum_score = _aggregate_scores(typed_max, method)
        rule_ids = {entry.rule_version_id for entry in entries}
        if len(rule_ids) != 1 or None in rule_ids:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} changed scoring-rule snapshot inside the week"
            )
        rule_version = first.rule_version
        if historical_snapshot is not None and historical_snapshot.rule_version_id != rule_version.id:
            raise WeeklyEvaluationConfigurationError(
                "Historical correction cannot replace the stored daily scoring-rule version"
            )
        scoring_details = {
            "source": "DAILY_SCORES",
            "aggregation_method": method.value,
            "daily_scores": typed_scores,
        }

    elif config.scoring_type == ScoringType.WEEKLY_AGGREGATED:
        if raw_total is None:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} requires numeric raw values for weekly scoring"
            )
        if historical_snapshot is not None:
            rule_version = historical_snapshot.rule_version
            if historical_snapshot.rule_version_id is not None and rule_version is None:
                raise WeeklyEvaluationConfigurationError(
                    "Stored historical scoring-rule version could not be loaded"
                )
        else:
            rule_version = await _resolve_weekly_rule_version(
                session, rule_id=config.scoring_rule_id, week_start=week_start
            )
        if rule_version is None:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} requires a weekly scoring rule"
            )
        if rule_version.scoring_rule.rule_type != RuleType.PERCENTAGE:
            raise WeeklyEvaluationConfigurationError(
                f"Unsupported weekly rule type for {first.activity.code}: {rule_version.scoring_rule.rule_type.value}"
            )
        if standard_version is None or standard_version.period != StandardPeriod.WEEKLY:
            raise WeeklyEvaluationConfigurationError(
                f"{first.activity.code} percentage scoring requires a WEEKLY standard"
            )
        final_score, scoring_details = _percentage_weekly_score(
            raw_total=raw_total,
            rule_version=rule_version,
            standard_version=standard_version,
        )
        maximum_score = rule_version.max_score

    elif config.scoring_type == ScoringType.NON_SCORED:
        final_score = None
        maximum_score = None
        scoring_details = {
            "source": "NON_SCORED_RAW_ANALYTICS",
            "aggregation_method": method.value,
        }
    else:
        raise WeeklyEvaluationConfigurationError(
            f"Unsupported scoring type: {config.scoring_type.value}"
        )

    if historical_snapshot is not None:
        if historical_snapshot.standard_version_id != (standard_version.id if standard_version else None):
            raise WeeklyEvaluationConfigurationError(
                "Historical correction cannot replace the stored standard version"
            )
        if historical_snapshot.rule_version_id != (rule_version.id if rule_version else None):
            raise WeeklyEvaluationConfigurationError(
                "Historical correction cannot replace the stored scoring-rule version"
            )

    details: dict[str, Any] = {
        "scoring": scoring_details,
        "standard": standard_details,
        "raw_field": next(iter(raw_field_keys)) if len(raw_field_keys) == 1 else None,
        "filled_days_for_raw_field": sum(1 for flag in raw_fill_flags if flag),
        "evaluated_days": 7,
    }

    return WeeklyActivityResult(
        weekly_evaluation_id=weekly_evaluation.id,
        activity_id=first.activity_id,
        category_activity_config_id=config.id,
        aggregation_method=method.value,
        raw_total=raw_total,
        daily_score_total=daily_score_total,
        final_activity_score=final_score,
        maximum_score=maximum_score,
        rule_version_id=rule_version.id if rule_version else None,
        standard_version_id=standard_version.id if standard_version else None,
        standard_snapshot=dict(standard_version.target_definition) if standard_version else None,
        standard_achievement=standard_achievement,
        calculation_details=details,
    )


async def generate_weekly_evaluation(
    session: AsyncSession,
    *,
    user: User,
    week_start: date,
    now_utc: datetime | None = None,
) -> WeeklyEvaluation:
    """Idempotently generate one official full-week evaluation.

    Policy A is enforced before any WeeklyEvaluation row is created: approval/reactivation
    midweek or deactivation midweek leaves Daily Cards as factual history but creates no
    official weekly score and performs no prorating.
    """

    existing_profile, organization = await _load_profile_and_org(session, user=user)
    existing = await _load_weekly_evaluation(
        session, profile_id=existing_profile.id, week_start=week_start
    )
    if existing is not None:
        return existing

    setting = await _setting_for_week(
        session, organization_id=organization.id, week_start=week_start
    )
    week_end = week_start + timedelta(days=6)
    now = now_utc or utc_now()
    today_in_week_timezone = organization_local_date(setting.timezone, now_utc=now)
    if today_in_week_timezone <= week_end:
        raise WeeklyEvaluationNotReadyError(
            "Official weekly evaluation is generated only after the complete local week has ended"
        )

    await _assert_full_lifecycle_week(
        session,
        user=user,
        week_start=week_start,
        timezone_name=setting.timezone,
    )

    cards = await _ensure_finalized_week_cards(
        session,
        user=user,
        profile=existing_profile,
        week_start=week_start,
        week_end=week_end,
        now_utc=now,
    )
    category_id, timezone_snapshot = _validate_week_snapshots(cards)

    evaluation = WeeklyEvaluation(
        organization_id=organization.id,
        devotee_profile_id=existing_profile.id,
        week_start_date=week_start,
        week_end_date=week_end,
        category_snapshot_id=category_id,
        timezone_snapshot=timezone_snapshot,
        sadhana_score=0,
        sadhana_max_score=0,
        sadhana_percentage=None,
        academic_score=0,
        academic_max_score=0,
        academic_percentage=None,
        revision_number=0,
        generated_at=now,
        updated_at=now,
    )
    session.add(evaluation)
    await session.flush()

    grouped = _entries_by_activity(cards)
    activity_lookup = {entry.activity_id: entry.activity for card in cards for entry in card.activity_entries}
    results: list[WeeklyActivityResult] = []
    for activity_id in sorted(grouped, key=lambda value: activity_lookup[value].code):
        result = await _build_activity_result(
            session,
            weekly_evaluation=evaluation,
            entries=grouped[activity_id],
            week_start=week_start,
        )
        session.add(result)
        results.append(result)

    sadhana_results = [
        result for result in results if activity_lookup[result.activity_id].category == ActivityCategory.SADHANA
    ]
    academic_results = [
        result for result in results if activity_lookup[result.activity_id].category == ActivityCategory.ACADEMIC
    ]

    evaluation.sadhana_score = sum(result.final_activity_score or 0 for result in sadhana_results)
    evaluation.sadhana_max_score = sum(result.maximum_score or 0 for result in sadhana_results)
    evaluation.sadhana_percentage = _percentage(
        evaluation.sadhana_score, evaluation.sadhana_max_score
    )
    evaluation.academic_score = sum(result.final_activity_score or 0 for result in academic_results)
    evaluation.academic_max_score = sum(result.maximum_score or 0 for result in academic_results)
    evaluation.academic_percentage = _percentage(
        evaluation.academic_score, evaluation.academic_max_score
    )

    await session.commit()
    loaded = await _load_weekly_evaluation(
        session, profile_id=existing_profile.id, week_start=week_start
    )
    if loaded is None:
        raise WeeklyEvaluationError("Weekly evaluation was created but could not be reloaded")
    return loaded


async def recalculate_existing_weekly_evaluation(
    session: AsyncSession,
    *,
    evaluation: WeeklyEvaluation,
    now_utc: datetime | None = None,
) -> WeeklyEvaluation:
    """Recalculate a persisted WeeklyEvaluation using only its stored historical snapshots.

    Historical Admin correction must not resolve whichever rule/standard is current today.
    Each existing WeeklyActivityResult therefore acts as the immutable reference set for
    category config, rule version, standard version, and aggregation method.
    """

    now = now_utc or utc_now()
    cards = await _load_week_cards(
        session,
        profile_id=evaluation.devotee_profile_id,
        week_start=evaluation.week_start_date,
        week_end=evaluation.week_end_date,
    )
    if len(cards) != 7 or any(card.status != CardStatus.FINALIZED for card in cards):
        raise WeeklyEvaluationNotReadyError(
            "Historical weekly recalculation requires seven finalized daily cards"
        )
    category_id, timezone_snapshot = _validate_week_snapshots(cards)
    if category_id != evaluation.category_snapshot_id:
        raise WeeklyEvaluationConfigurationError(
            "Historical correction cannot silently change the weekly category snapshot"
        )
    if timezone_snapshot != evaluation.timezone_snapshot:
        raise WeeklyEvaluationConfigurationError(
            "Historical correction cannot silently change the weekly timezone snapshot"
        )

    grouped = _entries_by_activity(cards)
    existing_by_activity = {row.activity_id: row for row in evaluation.activity_results}
    if set(grouped) != set(existing_by_activity):
        raise WeeklyEvaluationConfigurationError(
            "Historical correction cannot add or remove activities from an existing weekly result"
        )

    activity_lookup = {
        entry.activity_id: entry.activity
        for card in cards
        for entry in card.activity_entries
    }
    recalculated_rows: list[WeeklyActivityResult] = []
    for activity_id, entries in grouped.items():
        stored = existing_by_activity[activity_id]
        fresh = await _build_activity_result(
            session,
            weekly_evaluation=evaluation,
            entries=entries,
            week_start=evaluation.week_start_date,
            historical_snapshot=stored,
        )
        stored.raw_total = fresh.raw_total
        stored.daily_score_total = fresh.daily_score_total
        stored.final_activity_score = fresh.final_activity_score
        stored.maximum_score = fresh.maximum_score
        stored.standard_achievement = fresh.standard_achievement
        stored.standard_snapshot = fresh.standard_snapshot
        stored.calculation_details = fresh.calculation_details
        stored.updated_at = now
        recalculated_rows.append(stored)

    sadhana_rows = [
        row
        for row in recalculated_rows
        if activity_lookup[row.activity_id].category == ActivityCategory.SADHANA
    ]
    academic_rows = [
        row
        for row in recalculated_rows
        if activity_lookup[row.activity_id].category == ActivityCategory.ACADEMIC
    ]
    evaluation.sadhana_score = sum(row.final_activity_score or 0 for row in sadhana_rows)
    evaluation.sadhana_max_score = sum(row.maximum_score or 0 for row in sadhana_rows)
    evaluation.sadhana_percentage = _percentage(
        evaluation.sadhana_score, evaluation.sadhana_max_score
    )
    evaluation.academic_score = sum(row.final_activity_score or 0 for row in academic_rows)
    evaluation.academic_max_score = sum(row.maximum_score or 0 for row in academic_rows)
    evaluation.academic_percentage = _percentage(
        evaluation.academic_score, evaluation.academic_max_score
    )
    evaluation.revision_number += 1
    evaluation.updated_at = now
    return evaluation


async def rebuild_existing_weekly_evaluation_for_category_correction(
    session: AsyncSession,
    *,
    evaluation: WeeklyEvaluation,
    now_utc: datetime | None = None,
) -> WeeklyEvaluation:
    """Rebuild an existing week after an audited historical category correction.

    Unlike a raw-value correction, a category correction is explicitly allowed to
    replace the historical category/activity configuration set.  The rebuilt week uses
    only configuration, rule, and standard versions that were historically effective
    for that corrected category/week; it never resolves future/current versions.
    """

    now = now_utc or utc_now()
    cards = await _load_week_cards(
        session,
        profile_id=evaluation.devotee_profile_id,
        week_start=evaluation.week_start_date,
        week_end=evaluation.week_end_date,
    )
    if len(cards) != 7 or any(card.status != CardStatus.FINALIZED for card in cards):
        raise WeeklyEvaluationNotReadyError(
            "Historical category correction requires seven finalized cards for an existing official week"
        )

    category_id, timezone_snapshot = _validate_week_snapshots(cards)
    if timezone_snapshot != evaluation.timezone_snapshot:
        raise WeeklyEvaluationConfigurationError(
            "Historical category correction cannot change the weekly timezone snapshot"
        )

    # Category correction may legitimately add/remove applicable activities, so the
    # existing WeeklyActivityResult set is replaced rather than constrained to the old
    # snapshot IDs as in raw-value correction.
    for row in list(evaluation.activity_results):
        await session.delete(row)
    await session.flush()

    evaluation.category_snapshot_id = category_id
    grouped = _entries_by_activity(cards)
    activity_lookup = {
        entry.activity_id: entry.activity
        for card in cards
        for entry in card.activity_entries
    }
    results: list[WeeklyActivityResult] = []
    for activity_id in sorted(grouped, key=lambda value: activity_lookup[value].code):
        result = await _build_activity_result(
            session,
            weekly_evaluation=evaluation,
            entries=grouped[activity_id],
            week_start=evaluation.week_start_date,
        )
        session.add(result)
        results.append(result)

    sadhana_rows = [
        row
        for row in results
        if activity_lookup[row.activity_id].category == ActivityCategory.SADHANA
    ]
    academic_rows = [
        row
        for row in results
        if activity_lookup[row.activity_id].category == ActivityCategory.ACADEMIC
    ]
    evaluation.sadhana_score = sum(row.final_activity_score or 0 for row in sadhana_rows)
    evaluation.sadhana_max_score = sum(row.maximum_score or 0 for row in sadhana_rows)
    evaluation.sadhana_percentage = _percentage(
        evaluation.sadhana_score, evaluation.sadhana_max_score
    )
    evaluation.academic_score = sum(row.final_activity_score or 0 for row in academic_rows)
    evaluation.academic_max_score = sum(row.maximum_score or 0 for row in academic_rows)
    evaluation.academic_percentage = _percentage(
        evaluation.academic_score, evaluation.academic_max_score
    )
    evaluation.revision_number += 1
    evaluation.updated_at = now
    await session.flush()
    return evaluation


async def load_existing_weekly_evaluation_public(
    session: AsyncSession,
    *,
    evaluation: WeeklyEvaluation,
) -> WeeklyEvaluationPublic:
    loaded = await _load_weekly_evaluation(
        session,
        profile_id=evaluation.devotee_profile_id,
        week_start=evaluation.week_start_date,
    )
    if loaded is None:
        raise WeeklyEvaluationNotFoundError("Weekly evaluation not found")
    previous = await _previous_evaluation(
        session,
        profile_id=loaded.devotee_profile_id,
        week_start=loaded.week_start_date,
    )
    return serialize_weekly_evaluation(loaded, previous=previous)


async def _previous_evaluation(
    session: AsyncSession, *, profile_id: uuid.UUID, week_start: date
) -> WeeklyEvaluation | None:
    result = await session.execute(
        select(WeeklyEvaluation)
        .where(
            WeeklyEvaluation.devotee_profile_id == profile_id,
            WeeklyEvaluation.week_start_date < week_start,
        )
        .options(*_WEEKLY_LOAD_OPTIONS)
        .order_by(WeeklyEvaluation.week_start_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def serialize_weekly_evaluation(
    evaluation: WeeklyEvaluation,
    *,
    previous: WeeklyEvaluation | None = None,
) -> WeeklyEvaluationPublic:
    previous_by_activity = (
        {result.activity_id: result for result in previous.activity_results} if previous else {}
    )

    activities: list[WeeklyActivityResultPublic] = []
    for result in sorted(
        evaluation.activity_results,
        key=lambda row: (
            0 if row.activity.category == ActivityCategory.SADHANA else 1,
            row.activity.code,
        ),
    ):
        prior = previous_by_activity.get(result.activity_id)
        activities.append(
            WeeklyActivityResultPublic(
                activity_id=result.activity_id,
                code=result.activity.code,
                name=result.activity.name,
                category=result.activity.category,
                scoring_type=result.category_activity_config.scoring_type,
                aggregation_method=(
                    AggregationMethod(result.aggregation_method)
                    if result.aggregation_method is not None
                    else None
                ),
                raw_total=result.raw_total,
                daily_score_total=result.daily_score_total,
                final_activity_score=result.final_activity_score,
                maximum_score=result.maximum_score,
                rule_version_id=result.rule_version_id,
                standard_version_id=result.standard_version_id,
                standard_snapshot=result.standard_snapshot,
                standard_achievement=result.standard_achievement,
                calculation_details=result.calculation_details,
                previous_week=(
                    PreviousWeekActivityPublic(
                        week_start_date=previous.week_start_date,
                        raw_total=prior.raw_total,
                        final_activity_score=prior.final_activity_score,
                        maximum_score=prior.maximum_score,
                        standard_achievement=prior.standard_achievement,
                    )
                    if previous is not None and prior is not None
                    else None
                ),
            )
        )

    previous_public = None
    if previous is not None:
        previous_public = PreviousWeekEvaluationPublic(
            week_start_date=previous.week_start_date,
            week_end_date=previous.week_end_date,
            sadhana_score=previous.sadhana_score,
            sadhana_max_score=previous.sadhana_max_score,
            sadhana_percentage=previous.sadhana_percentage,
            academic_score=previous.academic_score,
            academic_max_score=previous.academic_max_score,
            academic_percentage=previous.academic_percentage,
        )

    return WeeklyEvaluationPublic(
        id=evaluation.id,
        week_start_date=evaluation.week_start_date,
        week_end_date=evaluation.week_end_date,
        category_code=evaluation.category_snapshot.code,
        category_name=evaluation.category_snapshot.display_name,
        timezone_snapshot=evaluation.timezone_snapshot,
        sadhana_score=evaluation.sadhana_score,
        sadhana_max_score=evaluation.sadhana_max_score,
        sadhana_percentage=evaluation.sadhana_percentage,
        academic_score=evaluation.academic_score,
        academic_max_score=evaluation.academic_max_score,
        academic_percentage=evaluation.academic_percentage,
        revision_number=evaluation.revision_number,
        generated_at=evaluation.generated_at,
        updated_at=evaluation.updated_at,
        activities=activities,
        previous_week=previous_public,
    )


async def get_weekly_evaluation_public(
    session: AsyncSession,
    *,
    user: User,
    week_start: date,
    now_utc: datetime | None = None,
) -> WeeklyEvaluationPublic:
    profile, _ = await _load_profile_and_org(session, user=user)
    evaluation = await generate_weekly_evaluation(
        session, user=user, week_start=week_start, now_utc=now_utc
    )
    previous = await _previous_evaluation(
        session, profile_id=profile.id, week_start=week_start
    )
    return serialize_weekly_evaluation(evaluation, previous=previous)


async def latest_completed_week_start(
    session: AsyncSession,
    *,
    user: User,
    now_utc: datetime | None = None,
) -> date:
    _, organization = await _load_profile_and_org(session, user=user)
    now = now_utc or utc_now()
    current_local_date = organization_local_date(organization.timezone, now_utc=now)
    current_start, _ = get_week_bounds(current_local_date, organization.week_start_day)
    prior_day = current_start - timedelta(days=1)

    # Resolve the settings that governed the day immediately before the current week,
    # so a recent week-start setting change does not reinterpret the previous week.
    result = await session.execute(
        select(OrganizationSettingVersion)
        .where(
            OrganizationSettingVersion.organization_id == organization.id,
            OrganizationSettingVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
            OrganizationSettingVersion.effective_from_week <= prior_day,
        )
        .order_by(OrganizationSettingVersion.effective_from_week.desc())
        .limit(1)
    )
    prior_setting = result.scalar_one_or_none()
    if prior_setting is None:
        raise WeeklyEvaluationConfigurationError(
            "No historical organization settings exist for the latest completed week"
        )
    previous_start, _ = get_week_bounds(prior_day, prior_setting.week_start_day)
    return previous_start


async def get_latest_weekly_evaluation_public(
    session: AsyncSession,
    *,
    user: User,
    now_utc: datetime | None = None,
) -> WeeklyEvaluationPublic:
    week_start = await latest_completed_week_start(session, user=user, now_utc=now_utc)
    return await get_weekly_evaluation_public(
        session, user=user, week_start=week_start, now_utc=now_utc
    )
