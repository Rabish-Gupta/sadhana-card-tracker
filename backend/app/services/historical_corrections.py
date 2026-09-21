from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import CardStatus, ChangeSource, ScoringType, UserRole
from app.core.timezone import get_week_bounds, organization_local_date, utc_now
from app.models.activity import Activity
from app.models.daily_card import DailyActivityEntry, DailyActivityValue, DailyCard
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.organization import Organization
from app.models.scoring import ScoringRuleVersion
from app.models.user import User
from app.models.weekly_evaluation import WeeklyActivityResult, WeeklyEvaluation
from app.schemas.historical_correction import (
    CategoryHistoryEntryPublic,
    HistoricalCardCorrectionRequest,
    HistoricalCardCorrectionResult,
    HistoricalCategoryCorrectionRequest,
    HistoricalCategoryCorrectionResult,
    HistoricalCategoryHistoryPublic,
)
from app.services.audit import add_audit_log
from app.services.daily_cards import (
    DailyCardConfigurationError,
    DailyCardValidationError,
    _apply_daily_scores,
    _apply_value_update,
    _CARD_LOAD_OPTIONS,
    _load_card,
    _recompute_entry_completion,
    _resolve_category_configs,
    _resolve_rule_versions,
    _resolve_setting_version_for_date,
    _validate_typed_update,
    serialize_daily_card,
)
from app.services.weekly_evaluations import (
    WeeklyEvaluationError,
    _WEEKLY_LOAD_OPTIONS,
    load_existing_weekly_evaluation_public,
    recalculate_existing_weekly_evaluation,
    rebuild_existing_weekly_evaluation_for_category_correction,
)


class HistoricalCorrectionError(ValueError):
    pass


class HistoricalCorrectionNotFoundError(HistoricalCorrectionError):
    pass


class HistoricalCorrectionConflictError(HistoricalCorrectionError):
    pass


class HistoricalCorrectionValidationError(HistoricalCorrectionError):
    pass


def _json_scalar(value: Decimal | Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def _value_snapshot(value: DailyActivityValue) -> dict[str, Any]:
    return {
        "field_id": str(value.activity_field_id),
        "field_key": value.activity_field.field_key,
        "is_filled": value.is_filled,
        "numeric_value": str(value.numeric_value),
        "time_value": value.time_value.isoformat() if value.time_value else None,
        "boolean_value": value.boolean_value,
        "text_value": value.text_value,
    }


def _entry_snapshot(entry: DailyActivityEntry) -> dict[str, Any]:
    return {
        "activity_id": str(entry.activity_id),
        "activity_code": entry.activity.code,
        "is_filled": entry.is_filled,
        "daily_score": entry.daily_score,
        "rule_version_id": str(entry.rule_version_id) if entry.rule_version_id else None,
        "category_activity_config_id": str(entry.category_activity_config_id),
        "values": [_value_snapshot(value) for value in entry.values],
    }


def _card_state_snapshot(card: DailyCard) -> dict[str, Any]:
    return {
        "card_id": str(card.id),
        "card_date": card.card_date.isoformat(),
        "category_snapshot_id": str(card.category_snapshot_id),
        "category_code": card.category_snapshot.code if card.category_snapshot else None,
        "status": card.status.value,
        "revision_number": card.revision_number,
        "activity_entries": [
            _entry_snapshot(entry)
            for entry in sorted(card.activity_entries, key=lambda item: item.activity.code)
        ],
    }


def _weekly_totals_snapshot(evaluation: WeeklyEvaluation) -> dict[str, Any]:
    return {
        "revision_number": evaluation.revision_number,
        "category_snapshot_id": str(evaluation.category_snapshot_id),
        "sadhana_score": evaluation.sadhana_score,
        "sadhana_max_score": evaluation.sadhana_max_score,
        "sadhana_percentage": _json_scalar(evaluation.sadhana_percentage),
        "academic_score": evaluation.academic_score,
        "academic_max_score": evaluation.academic_max_score,
        "academic_percentage": _json_scalar(evaluation.academic_percentage),
    }


def _weekly_state_snapshot(evaluation: WeeklyEvaluation) -> dict[str, Any]:
    payload = _weekly_totals_snapshot(evaluation)
    payload.update(
        {
            "evaluation_id": str(evaluation.id),
            "week_start_date": evaluation.week_start_date.isoformat(),
            "week_end_date": evaluation.week_end_date.isoformat(),
            "activity_results": [
                {
                    "activity_id": str(row.activity_id),
                    "activity_code": row.activity.code,
                    "category_activity_config_id": str(row.category_activity_config_id),
                    "rule_version_id": str(row.rule_version_id) if row.rule_version_id else None,
                    "standard_version_id": (
                        str(row.standard_version_id) if row.standard_version_id else None
                    ),
                    "raw_total": _json_scalar(row.raw_total),
                    "daily_score_total": row.daily_score_total,
                    "final_activity_score": row.final_activity_score,
                    "maximum_score": row.maximum_score,
                    "standard_achievement": _json_scalar(row.standard_achievement),
                }
                for row in sorted(evaluation.activity_results, key=lambda item: item.activity.code)
            ],
        }
    )
    return payload


def _history_row_snapshot(row: DevoteeCategoryHistory) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "previous_category_id": (
            str(row.previous_category_id) if row.previous_category_id else None
        ),
        "previous_category_code": (
            row.previous_category.code if row.previous_category is not None else None
        ),
        "new_category_id": str(row.new_category_id),
        "new_category_code": row.new_category.code,
        "effective_from_week": row.effective_from_week.isoformat(),
        "change_source": row.change_source.value,
        "reason": row.reason,
        "changed_by_id": str(row.changed_by_id) if row.changed_by_id else None,
    }


async def _load_target_devotee(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[User, DevoteeProfile, Organization]:
    result = await session.execute(
        select(User)
        .where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.role == UserRole.DEVOTEE,
            User.is_archived.is_(False),
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
    )
    user = result.scalar_one_or_none()
    if user is None or user.devotee_profile is None:
        raise HistoricalCorrectionNotFoundError("Devotee not found")
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise HistoricalCorrectionNotFoundError("Organization not found")
    return user, user.devotee_profile, organization


async def _load_category_history(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
) -> list[DevoteeCategoryHistory]:
    result = await session.execute(
        select(DevoteeCategoryHistory)
        .where(DevoteeCategoryHistory.devotee_profile_id == profile_id)
        .options(
            selectinload(DevoteeCategoryHistory.previous_category),
            selectinload(DevoteeCategoryHistory.new_category),
        )
        .order_by(DevoteeCategoryHistory.effective_from_week)
    )
    return list(result.scalars().all())


async def _weekly_evaluation_containing_card(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    card_date: date,
) -> WeeklyEvaluation | None:
    result = await session.execute(
        select(WeeklyEvaluation)
        .where(
            WeeklyEvaluation.devotee_profile_id == profile_id,
            WeeklyEvaluation.week_start_date <= card_date,
            WeeklyEvaluation.week_end_date >= card_date,
        )
        .options(*_WEEKLY_LOAD_OPTIONS)
    )
    rows = list(result.scalars().all())
    if len(rows) > 1:
        raise HistoricalCorrectionConflictError(
            "More than one weekly evaluation contains this card date"
        )
    return rows[0] if rows else None


async def get_finalized_card_for_admin(
    session: AsyncSession,
    *,
    admin: User,
    devotee_user_id: uuid.UUID,
    card_date: date,
):
    _, profile, organization = await _load_target_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=devotee_user_id,
    )
    card = await _load_card(session, profile_id=profile.id, card_date=card_date)
    if card is None:
        raise HistoricalCorrectionNotFoundError("Daily card not found")
    if card.status != CardStatus.FINALIZED:
        raise HistoricalCorrectionConflictError(
            "Historical correction is allowed only for finalized Daily Cards"
        )
    return serialize_daily_card(card, organization=organization)


async def correct_finalized_card(
    session: AsyncSession,
    *,
    admin: User,
    devotee_user_id: uuid.UUID,
    card_date: date,
    payload: HistoricalCardCorrectionRequest,
    now_utc: datetime | None = None,
) -> HistoricalCardCorrectionResult:
    """Correct raw historical values and deterministically recalculate derived results.

    The card's stored category/activity config and daily scoring-rule IDs are never replaced.
    If an official WeeklyEvaluation already exists, that exact persisted weekly result is
    recalculated from its stored config/rule/standard IDs rather than resolving today's
    active configuration.
    """

    now = now_utc or utc_now()
    _, profile, organization = await _load_target_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=devotee_user_id,
    )
    card = await _load_card(session, profile_id=profile.id, card_date=card_date)
    if card is None:
        raise HistoricalCorrectionNotFoundError("Daily card not found")
    if card.status != CardStatus.FINALIZED:
        raise HistoricalCorrectionConflictError(
            "Historical correction is allowed only for finalized Daily Cards"
        )

    entries_by_activity = {entry.activity_id: entry for entry in card.activity_entries}
    touched_entries: set[uuid.UUID] = set()
    before_entries: list[dict[str, Any]] = []

    for activity_update in payload.activities:
        entry = entries_by_activity.get(activity_update.activity_id)
        if entry is None:
            raise HistoricalCorrectionValidationError(
                "Activity is not part of this historical card snapshot"
            )
        if (
            entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED
            or entry.activity.is_system_derived
        ):
            raise HistoricalCorrectionValidationError(
                f"{entry.activity.name} is system-derived and cannot be directly corrected"
            )
        before_entries.append(_entry_snapshot(entry))
        values_by_field = {value.activity_field_id: value for value in entry.values}
        for value_update in activity_update.values:
            value = values_by_field.get(value_update.field_id)
            if value is None:
                raise HistoricalCorrectionValidationError(
                    "Field does not belong to the supplied activity on this historical card"
                )
            try:
                _validate_typed_update(value.activity_field, value_update)
            except DailyCardValidationError as exc:
                raise HistoricalCorrectionValidationError(str(exc)) from exc
            _apply_value_update(value, value_update, now)
        touched_entries.add(entry.id)

    if not touched_entries:
        raise HistoricalCorrectionValidationError("No historical values were supplied")

    # Completion and scores can have cross-activity consequences through Filling Sadhana Card,
    # so recompute every entry rather than only the activity directly edited by the Admin.
    for entry in card.activity_entries:
        if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
            entry.is_filled = True
        else:
            entry.is_filled = _recompute_entry_completion(entry)
    try:
        _apply_daily_scores(card, calculated_at=now, include_system_derived=True)
    except DailyCardConfigurationError as exc:
        raise HistoricalCorrectionConflictError(str(exc)) from exc
    card.revision_number += 1

    weekly = await _weekly_evaluation_containing_card(
        session,
        profile_id=profile.id,
        card_date=card.card_date,
    )
    weekly_before = _weekly_totals_snapshot(weekly) if weekly is not None else None
    if weekly is not None:
        try:
            await recalculate_existing_weekly_evaluation(
                session,
                evaluation=weekly,
                now_utc=now,
            )
        except WeeklyEvaluationError as exc:
            raise HistoricalCorrectionConflictError(str(exc)) from exc

    after_entries = [
        _entry_snapshot(entries_by_activity[item.activity_id])
        for item in payload.activities
    ]
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="DAILY_CARD",
        entity_id=card.id,
        action="HISTORICAL_CARD_CORRECTED",
        reason=payload.reason,
        before_data={
            "card_date": card.card_date,
            "revision_number": card.revision_number - 1,
            "corrected_entries": before_entries,
        },
        after_data={
            "card_date": card.card_date,
            "revision_number": card.revision_number,
            "corrected_entries": after_entries,
            "weekly_evaluation_id": weekly.id if weekly else None,
        },
        created_at=now,
    )

    if weekly is not None:
        await add_audit_log(
            session,
            organization_id=admin.organization_id,
            actor_user_id=admin.id,
            entity_type="WEEKLY_EVALUATION",
            entity_id=weekly.id,
            action="WEEKLY_EVALUATION_RECALCULATED",
            reason=f"Historical Daily Card correction for {card.card_date.isoformat()}: {payload.reason}",
            before_data=weekly_before,
            after_data=_weekly_totals_snapshot(weekly),
            created_at=now,
        )

    await session.commit()
    reloaded_card = await _load_card(session, profile_id=profile.id, card_date=card.card_date)
    if reloaded_card is None:
        raise HistoricalCorrectionNotFoundError("Corrected Daily Card could not be reloaded")

    weekly_public = None
    if weekly is not None:
        weekly_public = await load_existing_weekly_evaluation_public(
            session,
            evaluation=weekly,
        )

    return HistoricalCardCorrectionResult(
        devotee_user_id=devotee_user_id,
        card_date=card.card_date,
        card=serialize_daily_card(reloaded_card, organization=organization, now_utc=now),
        weekly_evaluation_recalculated=weekly is not None,
        weekly_evaluation=weekly_public,
    )


# ---------------------------------------------------------------------------
# Historical category correction — approved policy B
# ---------------------------------------------------------------------------


def _serialize_history(
    *,
    devotee_user_id: uuid.UUID,
    profile: DevoteeProfile,
    rows: list[DevoteeCategoryHistory],
) -> HistoricalCategoryHistoryPublic:
    return HistoricalCategoryHistoryPublic(
        devotee_user_id=devotee_user_id,
        current_category_code=profile.current_category.code,
        current_academic_year=profile.current_academic_year,
        history=[
            CategoryHistoryEntryPublic(
                id=row.id,
                previous_category_code=(
                    row.previous_category.code if row.previous_category is not None else None
                ),
                new_category_code=row.new_category.code,
                effective_from_week=row.effective_from_week,
                change_source=row.change_source.value,
                reason=row.reason,
                changed_by_id=row.changed_by_id,
            )
            for row in rows
        ],
    )


async def get_category_history_for_admin(
    session: AsyncSession,
    *,
    admin: User,
    devotee_user_id: uuid.UUID,
) -> HistoricalCategoryHistoryPublic:
    _, profile, _ = await _load_target_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=devotee_user_id,
    )
    rows = await _load_category_history(session, profile_id=profile.id)
    return _serialize_history(
        devotee_user_id=devotee_user_id,
        profile=profile,
        rows=rows,
    )


async def _target_category_by_code(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    code: str,
) -> DevoteeCategory:
    category = await session.scalar(
        select(DevoteeCategory).where(
            DevoteeCategory.organization_id == organization_id,
            DevoteeCategory.code == code,
        )
    )
    if category is None:
        raise HistoricalCorrectionValidationError("Target devotee category does not exist")
    return category


async def _reload_card_populated(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    card_date: date,
) -> DailyCard:
    result = await session.execute(
        select(DailyCard)
        .where(
            DailyCard.devotee_profile_id == profile_id,
            DailyCard.card_date == card_date,
        )
        .options(*_CARD_LOAD_OPTIONS)
        .execution_options(populate_existing=True)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise HistoricalCorrectionNotFoundError("Daily Card disappeared during correction")
    return card


async def _rebuild_card_for_corrected_category(
    session: AsyncSession,
    *,
    card: DailyCard,
    target_category: DevoteeCategory,
    organization: Organization,
    now_utc: datetime,
) -> tuple[DailyCard, dict[str, Any], dict[str, Any]]:
    """Rebind one persisted card to the category/configuration effective for its week.

    Overlapping activities retain their exact raw values.  Activities that were present
    only because of the wrong category are removed from the corrected card (their full
    original raw snapshot is retained in AuditLog).  Newly applicable activities are
    materialized as genuinely missing/N/A values rather than fabricated performance.
    """

    before = _card_state_snapshot(card)
    setting = await _resolve_setting_version_for_date(
        session,
        organization_id=organization.id,
        target_date=card.card_date,
    )
    week_start, _ = get_week_bounds(card.card_date, setting.week_start_day)
    configs = await _resolve_category_configs(
        session,
        organization_id=organization.id,
        category_id=target_category.id,
        week_start=week_start,
    )
    if not configs:
        raise HistoricalCorrectionConflictError(
            f"No historical category/activity configuration exists for {target_category.code} "
            f"in week {week_start.isoformat()}"
        )

    daily_rule_ids = {
        config.scoring_rule_id
        for config in configs
        if config.scoring_rule_id is not None
        and config.scoring_type in {ScoringType.DAILY, ScoringType.SYSTEM_DERIVED}
    }
    rule_versions = await _resolve_rule_versions(
        session,
        rule_ids=set(daily_rule_ids),
        week_start=week_start,
    )
    configs_by_activity = {config.activity_id: config for config in configs}
    existing_by_activity = {entry.activity_id: entry for entry in card.activity_entries}

    # Remove activities that do not belong to the corrected category/week.  Their raw
    # values are preserved in the before snapshot written to the append-only audit log.
    for activity_id, entry in list(existing_by_activity.items()):
        if activity_id in configs_by_activity:
            continue
        for value in list(entry.values):
            await session.delete(value)
        await session.delete(entry)

    for config in configs:
        rule_version = None
        max_score = None
        if config.scoring_type in {ScoringType.DAILY, ScoringType.SYSTEM_DERIVED}:
            if config.scoring_rule_id is None:
                raise HistoricalCorrectionConflictError(
                    f"{config.activity.code} has no scoring rule for the corrected week"
                )
            rule_version = rule_versions.get(config.scoring_rule_id)
            if rule_version is None:
                raise HistoricalCorrectionConflictError(
                    f"No historical scoring-rule version exists for {config.activity.code} "
                    f"in week {week_start.isoformat()}"
                )
            max_score = rule_version.max_score

        entry = existing_by_activity.get(config.activity_id)
        if entry is None:
            entry = DailyActivityEntry(
                daily_card_id=card.id,
                activity_id=config.activity_id,
                category_activity_config_id=config.id,
                is_filled=False,
                daily_score=None,
                rule_version_id=rule_version.id if rule_version else None,
                max_score_snapshot=max_score,
                score_calculated_at=None,
                score_details=None,
            )
            session.add(entry)
            await session.flush()

            if config.scoring_type != ScoringType.SYSTEM_DERIVED and not config.activity.is_system_derived:
                fields = [
                    field
                    for field in config.activity.fields
                    if field.is_active and not field.is_archived
                ]
                if not fields:
                    raise HistoricalCorrectionConflictError(
                        f"Cannot reconstruct {config.activity.code}: no usable activity fields exist"
                    )
                for field in fields:
                    session.add(
                        DailyActivityValue(
                            daily_activity_entry_id=entry.id,
                            activity_field_id=field.id,
                            is_filled=False,
                            numeric_value=Decimal("0"),
                            time_value=None,
                            boolean_value=None,
                            text_value=None,
                        )
                    )
        else:
            entry.category_activity_config_id = config.id
            entry.category_activity_config = config
            entry.rule_version_id = rule_version.id if rule_version else None
            entry.rule_version = rule_version
            entry.max_score_snapshot = max_score
            entry.daily_score = None
            entry.score_calculated_at = None
            entry.score_details = None

    card.category_snapshot_id = target_category.id
    card.category_snapshot = target_category
    await session.flush()

    refreshed = await _reload_card_populated(
        session,
        profile_id=card.devotee_profile_id,
        card_date=card.card_date,
    )
    for entry in refreshed.activity_entries:
        if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
            entry.is_filled = refreshed.status == CardStatus.FINALIZED
        else:
            entry.is_filled = _recompute_entry_completion(entry)
    try:
        _apply_daily_scores(
            refreshed,
            calculated_at=now_utc,
            include_system_derived=refreshed.status == CardStatus.FINALIZED,
        )
    except DailyCardConfigurationError as exc:
        raise HistoricalCorrectionConflictError(str(exc)) from exc
    refreshed.revision_number += 1
    await session.flush()
    after = _card_state_snapshot(refreshed)
    return refreshed, before, after


async def _load_affected_cards(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    start_date: date,
    end_exclusive: date | None,
) -> list[DailyCard]:
    statement = select(DailyCard).where(
        DailyCard.devotee_profile_id == profile_id,
        DailyCard.card_date >= start_date,
    )
    if end_exclusive is not None:
        statement = statement.where(DailyCard.card_date < end_exclusive)
    result = await session.execute(
        statement.options(*_CARD_LOAD_OPTIONS).order_by(DailyCard.card_date)
    )
    return list(result.scalars().all())


async def _load_affected_weekly_evaluations(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    start_week: date,
    end_exclusive: date | None,
) -> list[WeeklyEvaluation]:
    statement = select(WeeklyEvaluation).where(
        WeeklyEvaluation.devotee_profile_id == profile_id,
        WeeklyEvaluation.week_start_date >= start_week,
    )
    if end_exclusive is not None:
        statement = statement.where(WeeklyEvaluation.week_start_date < end_exclusive)
    result = await session.execute(
        statement.options(*_WEEKLY_LOAD_OPTIONS).order_by(WeeklyEvaluation.week_start_date)
    )
    return list(result.scalars().all())


async def correct_historical_category(
    session: AsyncSession,
    *,
    admin: User,
    devotee_user_id: uuid.UUID,
    payload: HistoricalCategoryCorrectionRequest,
    now_utc: datetime | None = None,
) -> HistoricalCategoryCorrectionResult:
    """Apply approved policy B for an audited historical category correction.

    The corrected category starts at ``effective_from_week`` and continues until the next
    *actual* different recorded transition.  Existing Daily Cards in that interval are
    rebound to category/config/rule versions that were effective in their historical
    week.  Existing official WeeklyEvaluations are rebuilt from those corrected card
    snapshots.  No current/future rule or standard version is used to rewrite history.
    """

    now = now_utc or utc_now()
    batch_id = uuid.uuid4()
    user, profile, organization = await _load_target_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=devotee_user_id,
    )
    target_category = await _target_category_by_code(
        session,
        organization_id=organization.id,
        code=payload.target_category_code,
    )

    try:
        setting = await _resolve_setting_version_for_date(
            session,
            organization_id=organization.id,
            target_date=payload.effective_from_week,
        )
    except DailyCardConfigurationError as exc:
        raise HistoricalCorrectionConflictError(str(exc)) from exc
    canonical_week, _ = get_week_bounds(
        payload.effective_from_week,
        setting.week_start_day,
    )
    if (
        canonical_week != payload.effective_from_week
        and setting.effective_from_week != payload.effective_from_week
    ):
        raise HistoricalCorrectionValidationError(
            "effective_from_week must be an organization week boundary"
        )

    history = await _load_category_history(session, profile_id=profile.id)
    if not history:
        raise HistoricalCorrectionConflictError("Devotee has no category history")
    before_history = [_history_row_snapshot(row) for row in history]

    prior = None
    row_at = None
    for row in history:
        if row.effective_from_week < payload.effective_from_week:
            prior = row
        elif row.effective_from_week == payload.effective_from_week:
            row_at = row
            break
        else:
            break

    original_category = row_at.new_category if row_at is not None else (
        prior.new_category if prior is not None else None
    )
    if original_category is None:
        raise HistoricalCorrectionValidationError(
            "Correction cannot start before the devotee's first recorded category week"
        )
    if original_category.id == target_category.id:
        raise HistoricalCorrectionConflictError(
            "The requested category is already effective for that week"
        )

    # Ensure the corrected category has an executable historical configuration at the
    # correction boundary before mutating category history.
    configs = await _resolve_category_configs(
        session,
        organization_id=organization.id,
        category_id=target_category.id,
        week_start=payload.effective_from_week,
    )
    if not configs:
        raise HistoricalCorrectionConflictError(
            "Target category has no historical activity configuration for the correction week"
        )

    removed_rows: list[dict[str, Any]] = []
    correction_row: DevoteeCategoryHistory | None = row_at
    if row_at is None:
        if prior is None:
            raise HistoricalCorrectionValidationError(
                "A category correction inside history requires a prior category transition"
            )
        if prior.new_category_id == target_category.id:
            raise HistoricalCorrectionConflictError(
                "The target category is already effective before this week"
            )
        correction_row = DevoteeCategoryHistory(
            devotee_profile_id=profile.id,
            previous_category_id=prior.new_category_id,
            new_category_id=target_category.id,
            effective_from_week=payload.effective_from_week,
            change_source=ChangeSource.ADMIN,
            reason=payload.reason,
            changed_by_id=admin.id,
            created_at=now,
        )
        correction_row.previous_category = prior.new_category
        correction_row.new_category = target_category
        session.add(correction_row)
    elif prior is not None and prior.new_category_id == target_category.id:
        # The old row introduced the wrong category; correcting back to the preceding
        # category means that transition should not exist at all.
        removed_rows.append(_history_row_snapshot(row_at))
        await session.delete(row_at)
        correction_row = None
    else:
        row_at.previous_category_id = prior.new_category_id if prior is not None else None
        row_at.previous_category = prior.new_category if prior is not None else None
        row_at.new_category_id = target_category.id
        row_at.new_category = target_category
        row_at.change_source = ChangeSource.ADMIN
        row_at.reason = payload.reason
        row_at.changed_by_id = admin.id

    # Policy B: corrected category persists until the next *different* transition.
    # A future/history row that transitions to the same corrected category becomes a
    # no-op and is removed; the next different row is repaired to reference the corrected
    # category as its previous category.
    future_rows = [
        row for row in history if row.effective_from_week > payload.effective_from_week
    ]
    next_surviving: DevoteeCategoryHistory | None = None
    for row in future_rows:
        if row.new_category_id == target_category.id:
            removed_rows.append(_history_row_snapshot(row))
            await session.delete(row)
            continue
        row.previous_category_id = target_category.id
        row.previous_category = target_category
        next_surviving = row
        break

    await session.flush()
    effective_until = (
        next_surviving.effective_from_week if next_surviving is not None else None
    )

    affected_cards = await _load_affected_cards(
        session,
        profile_id=profile.id,
        start_date=payload.effective_from_week,
        end_exclusive=effective_until,
    )
    rebuilt_cards = 0
    for card in affected_cards:
        rebuilt, before_card, after_card = await _rebuild_card_for_corrected_category(
            session,
            card=card,
            target_category=target_category,
            organization=organization,
            now_utc=now,
        )
        await add_audit_log(
            session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            entity_type="DAILY_CARD",
            entity_id=rebuilt.id,
            action="HISTORICAL_CARD_CATEGORY_REBUILT",
            reason=payload.reason,
            before_data={
                "correction_batch_id": batch_id,
                "category_correction_effective_from_week": payload.effective_from_week,
                "card": before_card,
            },
            after_data={
                "correction_batch_id": batch_id,
                "category_correction_effective_from_week": payload.effective_from_week,
                "card": after_card,
            },
            created_at=now,
        )
        rebuilt_cards += 1

    affected_weeks = await _load_affected_weekly_evaluations(
        session,
        profile_id=profile.id,
        start_week=payload.effective_from_week,
        end_exclusive=effective_until,
    )
    rebuilt_weeks = 0
    for evaluation in affected_weeks:
        before_week = _weekly_state_snapshot(evaluation)
        try:
            await rebuild_existing_weekly_evaluation_for_category_correction(
                session,
                evaluation=evaluation,
                now_utc=now,
            )
        except WeeklyEvaluationError as exc:
            raise HistoricalCorrectionConflictError(str(exc)) from exc
        await session.flush()
        # Reload with result relationships so the audit snapshot reflects the new set.
        refreshed = await session.scalar(
            select(WeeklyEvaluation)
            .where(WeeklyEvaluation.id == evaluation.id)
            .options(*_WEEKLY_LOAD_OPTIONS)
            .execution_options(populate_existing=True)
        )
        if refreshed is None:
            raise HistoricalCorrectionNotFoundError(
                "Weekly evaluation disappeared during category correction"
            )
        await add_audit_log(
            session,
            organization_id=organization.id,
            actor_user_id=admin.id,
            entity_type="WEEKLY_EVALUATION",
            entity_id=refreshed.id,
            action="WEEKLY_EVALUATION_CATEGORY_REBUILT",
            reason=payload.reason,
            before_data={
                "correction_batch_id": batch_id,
                "weekly_evaluation": before_week,
            },
            after_data={
                "correction_batch_id": batch_id,
                "weekly_evaluation": _weekly_state_snapshot(refreshed),
            },
            created_at=now,
        )
        rebuilt_weeks += 1

    # Re-resolve the currently effective category from the corrected history.  This may
    # change the materialized profile if the corrected interval reaches the present.
    local_today = organization_local_date(organization.timezone, now_utc=now)
    current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
    current_history = await session.scalar(
        select(DevoteeCategoryHistory)
        .where(
            DevoteeCategoryHistory.devotee_profile_id == profile.id,
            DevoteeCategoryHistory.effective_from_week <= current_week_start,
        )
        .options(selectinload(DevoteeCategoryHistory.new_category))
        .order_by(DevoteeCategoryHistory.effective_from_week.desc())
        .limit(1)
    )
    if current_history is None:
        raise HistoricalCorrectionConflictError(
            "Corrected category history no longer resolves a current category"
        )
    old_current_category_id = profile.current_category_id
    profile.current_category_id = current_history.new_category_id
    profile.current_category = current_history.new_category
    profile.current_academic_year = current_history.new_category.academic_year
    current_profile_updated = old_current_category_id != profile.current_category_id

    await session.flush()
    after_history_rows = await _load_category_history(session, profile_id=profile.id)
    after_history = [_history_row_snapshot(row) for row in after_history_rows]
    await add_audit_log(
        session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        entity_type="DEVOTEE_PROFILE",
        entity_id=profile.id,
        action="HISTORICAL_CATEGORY_CORRECTED",
        reason=payload.reason,
        before_data={
            "correction_batch_id": batch_id,
            "effective_from_week": payload.effective_from_week,
            "original_category_code": original_category.code,
            "history": before_history,
        },
        after_data={
            "correction_batch_id": batch_id,
            "effective_from_week": payload.effective_from_week,
            "effective_until_exclusive": effective_until,
            "corrected_category_code": target_category.code,
            "next_transition_category_code": (
                next_surviving.new_category.code if next_surviving is not None else None
            ),
            "history_rows_removed_as_redundant": removed_rows,
            "history": after_history,
            "affected_daily_cards": rebuilt_cards,
            "affected_weekly_evaluations": rebuilt_weeks,
            "current_profile_updated": current_profile_updated,
            "current_category_code": profile.current_category.code,
            "current_academic_year": profile.current_academic_year,
        },
        created_at=now,
    )

    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise

    return HistoricalCategoryCorrectionResult(
        devotee_user_id=devotee_user_id,
        correction_batch_id=batch_id,
        effective_from_week=payload.effective_from_week,
        effective_until_exclusive=effective_until,
        previous_category_code=original_category.code,
        corrected_category_code=target_category.code,
        next_transition_category_code=(
            next_surviving.new_category.code if next_surviving is not None else None
        ),
        history_rows_removed_as_redundant=len(removed_rows),
        affected_daily_cards=rebuilt_cards,
        affected_weekly_evaluations=rebuilt_weeks,
        current_profile_updated=current_profile_updated,
        current_category_code=profile.current_category.code,
        current_academic_year=profile.current_academic_year,
    )
