from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    ActivityInputType,
    CardStatus,
    ScoringType,
    VersionStatus,
)
from app.core.timezone import (
    get_week_bounds,
    local_deadline_to_utc,
    organization_local_date,
    to_organization_time,
    utc_now,
)
from app.models.activity import Activity, ActivityField
from app.models.daily_card import DailyActivityEntry, DailyActivityValue, DailyCard
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.scoring import ScoringRuleVersion
from app.services.scoring import ScoringConfigurationError, evaluate_daily_entry
from app.models.user import User
from app.schemas.daily_card import (
    DailyActivityPublic,
    DailyActivityValuePublic,
    DailyCardPublic,
    DailyCardUpdateRequest,
)


class DailyCardError(ValueError):
    pass


class DailyCardNotFoundError(DailyCardError):
    pass


class DailyCardNotEditableError(DailyCardError):
    pass


class DailyCardValidationError(DailyCardError):
    pass


class DailyCardConfigurationError(DailyCardError):
    pass


_CARD_LOAD_OPTIONS = (
    selectinload(DailyCard.category_snapshot),
    selectinload(DailyCard.activity_entries)
    .selectinload(DailyActivityEntry.activity)
    .selectinload(Activity.fields),
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


def _version_is_historically_eligible(status: VersionStatus) -> bool:
    return status in {VersionStatus.ACTIVE, VersionStatus.ARCHIVED}


def compute_activity_completion(
    *,
    fields: Iterable[ActivityField],
    values: Iterable[DailyActivityValue],
    rule_configuration: dict | None,
) -> bool:
    """Return factual form-completion state; this does not award any score.

    Missing and intentionally-entered zero/False stay distinct because completion uses
    ``is_filled`` rather than truthiness. Chanting uses the approved conditional rule:
    rounds below the required count are a complete entry without completion time, while
    reaching the required rounds makes completion time mandatory.
    """

    # ``fields`` must represent the fields snapshotted onto this card entry. Once a
    # DailyActivityValue exists, later activity-field archival must not remove that
    # field from an already-created card.
    field_list = list(fields)
    if not field_list:
        return False

    values_by_field_id = {value.activity_field_id: value for value in values}
    values_by_key: dict[str, DailyActivityValue] = {}
    fields_by_key = {field.field_key: field for field in field_list}
    for field in field_list:
        value = values_by_field_id.get(field.id)
        if value is not None:
            values_by_key[field.field_key] = value

    for field in field_list:
        if not field.required_for_completion:
            continue
        value = values_by_field_id.get(field.id)
        if value is None or not value.is_filled:
            return False

    config = rule_configuration or {}
    rounds_key = config.get("rounds_field")
    completion_key = config.get("completion_field")
    required_rounds = config.get("required_rounds")
    if rounds_key and completion_key and required_rounds is not None:
        rounds_field = fields_by_key.get(str(rounds_key))
        completion_field = fields_by_key.get(str(completion_key))
        if rounds_field is not None and completion_field is not None:
            rounds_value = values_by_key.get(str(rounds_key))
            if rounds_value is None or not rounds_value.is_filled:
                return False
            rounds = rounds_value.numeric_value
            if rounds >= Decimal(str(required_rounds)):
                completion_value = values_by_key.get(str(completion_key))
                if completion_value is None or not completion_value.is_filled:
                    return False

    return True


def _validate_typed_update(field: ActivityField, update) -> None:
    if not update.is_filled:
        return

    numeric_types = {
        ActivityInputType.NUMBER,
        ActivityInputType.COUNT,
        ActivityInputType.DURATION,
    }
    if field.input_type in numeric_types:
        if update.numeric_value is None:
            raise DailyCardValidationError(
                f"{field.field_key} requires numeric_value"
            )
        if field.input_type in {ActivityInputType.COUNT, ActivityInputType.DURATION}:
            if update.numeric_value < 0:
                raise DailyCardValidationError(
                    f"{field.field_key} cannot be negative"
                )
        if field.input_type == ActivityInputType.COUNT:
            if update.numeric_value != update.numeric_value.to_integral_value():
                raise DailyCardValidationError(
                    f"{field.field_key} must be a whole-number count"
                )
        return

    if field.input_type == ActivityInputType.TIME:
        if update.time_value is None:
            raise DailyCardValidationError(f"{field.field_key} requires time_value")
        return

    if field.input_type == ActivityInputType.BOOLEAN:
        if update.boolean_value is None:
            raise DailyCardValidationError(f"{field.field_key} requires boolean_value")
        return

    if field.input_type in {ActivityInputType.TEXT, ActivityInputType.SELECTION}:
        if update.text_value is None or not update.text_value.strip():
            raise DailyCardValidationError(f"{field.field_key} requires text_value")
        return

    raise DailyCardValidationError(f"Unsupported field input type: {field.input_type.value}")


def _apply_value_update(value: DailyActivityValue, update, now_utc: datetime) -> None:
    value.is_filled = update.is_filled
    value.numeric_value = update.numeric_value if update.numeric_value is not None else Decimal("0")
    value.time_value = update.time_value
    value.boolean_value = update.boolean_value
    value.text_value = update.text_value
    value.updated_at = now_utc


async def _load_devotee_context(
    session: AsyncSession,
    *,
    user: User,
) -> tuple[DevoteeProfile, Organization]:
    result = await session.execute(
        select(DevoteeProfile, Organization)
        .join(User, User.id == DevoteeProfile.user_id)
        .join(Organization, Organization.id == User.organization_id)
        .where(
            DevoteeProfile.user_id == user.id,
            Organization.id == user.organization_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise DailyCardNotFoundError("Devotee profile or organization not found")
    return row[0], row[1]


async def _resolve_setting_version_for_date(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    target_date: date,
) -> OrganizationSettingVersion:
    result = await session.execute(
        select(OrganizationSettingVersion)
        .where(
            OrganizationSettingVersion.organization_id == organization_id,
            OrganizationSettingVersion.status.in_(
                [VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
            OrganizationSettingVersion.effective_from_week <= target_date,
        )
        .order_by(OrganizationSettingVersion.effective_from_week.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise DailyCardConfigurationError(
            "No effective organization settings version exists for this date"
        )
    return version


async def _resolve_category_for_week(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    week_start: date,
) -> DevoteeCategory:
    result = await session.execute(
        select(DevoteeCategory)
        .join(
            DevoteeCategoryHistory,
            DevoteeCategoryHistory.new_category_id == DevoteeCategory.id,
        )
        .where(
            DevoteeCategoryHistory.devotee_profile_id == profile_id,
            DevoteeCategoryHistory.effective_from_week <= week_start,
        )
        .order_by(DevoteeCategoryHistory.effective_from_week.desc())
        .limit(1)
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise DailyCardNotFoundError(
            "No devotee category was effective for the requested week"
        )
    return category


async def _resolve_category_configs(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    category_id: uuid.UUID,
    week_start: date,
) -> list[CategoryActivityConfig]:
    result = await session.execute(
        select(CategoryActivityConfig)
        .where(
            CategoryActivityConfig.organization_id == organization_id,
            CategoryActivityConfig.category_id == category_id,
            CategoryActivityConfig.status.in_(
                [VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
            CategoryActivityConfig.effective_from_week <= week_start,
        )
        .options(
            selectinload(CategoryActivityConfig.activity).selectinload(Activity.fields)
        )
        .order_by(CategoryActivityConfig.effective_from_week.desc())
    )
    rows = list(result.scalars().all())
    latest_by_activity: dict[uuid.UUID, CategoryActivityConfig] = {}
    for config in rows:
        latest_by_activity.setdefault(config.activity_id, config)

    configs = [config for config in latest_by_activity.values() if config.is_applicable]
    configs.sort(
        key=lambda config: (
            config.activity.category.value,
            config.activity.created_at,
            config.activity.code,
        )
    )
    return configs


async def _resolve_rule_versions(
    session: AsyncSession,
    *,
    rule_ids: set[uuid.UUID],
    week_start: date,
) -> dict[uuid.UUID, ScoringRuleVersion]:
    if not rule_ids:
        return {}
    result = await session.execute(
        select(ScoringRuleVersion)
        .where(
            ScoringRuleVersion.scoring_rule_id.in_(rule_ids),
            ScoringRuleVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
            ScoringRuleVersion.effective_from_week <= week_start,
        )
        .options(selectinload(ScoringRuleVersion.scoring_rule))
        .order_by(ScoringRuleVersion.effective_from_week.desc())
    )
    latest: dict[uuid.UUID, ScoringRuleVersion] = {}
    for version in result.scalars().all():
        latest.setdefault(version.scoring_rule_id, version)
    return latest


async def _load_card(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    card_date: date,
) -> DailyCard | None:
    result = await session.execute(
        select(DailyCard)
        .where(
            DailyCard.devotee_profile_id == profile_id,
            DailyCard.card_date == card_date,
        )
        .options(*_CARD_LOAD_OPTIONS)
    )
    return result.scalar_one_or_none()


async def _create_card(
    session: AsyncSession,
    *,
    user: User,
    profile: DevoteeProfile,
    organization: Organization,
    target_date: date,
) -> DailyCard:
    setting_version = await _resolve_setting_version_for_date(
        session,
        organization_id=organization.id,
        target_date=target_date,
    )
    week_start, _ = get_week_bounds(target_date, setting_version.week_start_day)
    category = await _resolve_category_for_week(
        session,
        profile_id=profile.id,
        week_start=week_start,
    )
    configs = await _resolve_category_configs(
        session,
        organization_id=organization.id,
        category_id=category.id,
        week_start=week_start,
    )
    if not configs:
        raise DailyCardConfigurationError(
            "No applicable category/activity configuration exists for this week"
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

    card = DailyCard(
        organization_id=organization.id,
        devotee_profile_id=profile.id,
        card_date=target_date,
        category_snapshot_id=category.id,
        status=CardStatus.IN_PROGRESS,
        timezone_snapshot=setting_version.timezone,
        deadline_time_snapshot=setting_version.daily_finalize_time,
        deadline_at_utc=local_deadline_to_utc(
            target_date,
            setting_version.daily_finalize_time,
            setting_version.timezone,
        ),
        revision_number=0,
    )
    session.add(card)
    await session.flush()

    for config in configs:
        rule_version = None
        max_score = None
        if config.scoring_type in {ScoringType.DAILY, ScoringType.SYSTEM_DERIVED}:
            if config.scoring_rule_id is None:
                raise DailyCardConfigurationError(
                    f"{config.activity.code} requires a daily scoring rule"
                )
            rule_version = rule_versions.get(config.scoring_rule_id)
            if rule_version is None:
                raise DailyCardConfigurationError(
                    f"No effective scoring-rule version for {config.activity.code}"
                )
            max_score = rule_version.max_score

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

        if config.scoring_type == ScoringType.SYSTEM_DERIVED or config.activity.is_system_derived:
            continue

        for field in config.activity.fields:
            if not field.is_active or field.is_archived:
                continue
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

    try:
        await session.commit()
    except IntegrityError:
        # Concurrent GET /today requests can race on the unique devotee/date key.
        await session.rollback()
        existing = await _load_card(
            session,
            profile_id=profile.id,
            card_date=target_date,
        )
        if existing is not None:
            return existing
        raise

    created = await _load_card(session, profile_id=profile.id, card_date=target_date)
    if created is None:
        raise DailyCardError("Daily card was created but could not be reloaded")
    return created




def _apply_daily_scores(
    card: DailyCard,
    *,
    calculated_at: datetime,
    include_system_derived: bool,
) -> None:
    """Recalculate deterministic per-day scores from snapshotted config + raw values.

    This never resolves current rules.  It uses only the exact CategoryActivityConfig and
    ScoringRuleVersion already stored on each DailyActivityEntry, which is the project
    invariant required for historical recalculation.
    """

    try:
        for entry in card.activity_entries:
            outcome = evaluate_daily_entry(
                entry,
                card_entries=card.activity_entries,
                allow_system_derived=include_system_derived,
            )
            if (
                entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED
                and not include_system_derived
            ):
                # Filling-card marks are intentionally decided only at finalization.
                entry.daily_score = None
                entry.score_calculated_at = None
                entry.score_details = None
                continue
            if entry.category_activity_config.scoring_type in {
                ScoringType.WEEKLY_AGGREGATED,
                ScoringType.NON_SCORED,
            }:
                entry.daily_score = None
                entry.score_calculated_at = None
                entry.score_details = None
                continue
            entry.daily_score = outcome.score
            entry.score_calculated_at = calculated_at
            entry.score_details = outcome.details
    except ScoringConfigurationError as exc:
        raise DailyCardConfigurationError(str(exc)) from exc


def _finalized_card_needs_scoring(card: DailyCard) -> bool:
    """Detect v0.6/legacy finalized cards whose scores have not yet been generated."""

    for entry in card.activity_entries:
        if entry.category_activity_config.scoring_type in {
            ScoringType.DAILY,
            ScoringType.SYSTEM_DERIVED,
        } and (entry.daily_score is None or entry.score_calculated_at is None):
            return True
    return False

def _recompute_entry_completion(entry: DailyActivityEntry) -> bool:
    if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
        return entry.daily_card.status == CardStatus.FINALIZED
    configuration = entry.rule_version.configuration if entry.rule_version else None
    return compute_activity_completion(
        fields=[value.activity_field for value in entry.values],
        values=entry.values,
        rule_configuration=configuration,
    )


async def _finalize_if_due(
    session: AsyncSession,
    *,
    card: DailyCard,
    now_utc: datetime,
) -> DailyCard:
    if card.status == CardStatus.FINALIZED:
        # Step 9 compatibility: cards finalized by v0.6 may have raw data + exact
        # snapshots but NULL scores. Lazily backfill them from those historical IDs.
        if _finalized_card_needs_scoring(card):
            for entry in card.activity_entries:
                if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
                    entry.is_filled = True
                else:
                    entry.is_filled = _recompute_entry_completion(entry)
            _apply_daily_scores(
                card,
                calculated_at=now_utc,
                include_system_derived=True,
            )
            await session.commit()
            reloaded = await _load_card(
                session,
                profile_id=card.devotee_profile_id,
                card_date=card.card_date,
            )
            if reloaded is None:
                raise DailyCardError("Scored card could not be reloaded")
            return reloaded
        return card

    if now_utc < card.deadline_at_utc:
        return card

    card.status = CardStatus.FINALIZED
    # Logical auto-finalization time is the configured/snapshotted deadline even if a
    # worker/request notices it slightly later.
    card.finalized_at = card.deadline_at_utc
    for entry in card.activity_entries:
        if entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED:
            entry.is_filled = True
        else:
            entry.is_filled = _recompute_entry_completion(entry)

    # Filling-card depends on the final completion state of every countable activity,
    # so it must be evaluated only after all completion flags have been recomputed.
    _apply_daily_scores(
        card,
        calculated_at=now_utc,
        include_system_derived=True,
    )
    await session.commit()
    finalized = await _load_card(
        session,
        profile_id=card.devotee_profile_id,
        card_date=card.card_date,
    )
    if finalized is None:
        raise DailyCardError("Finalized card could not be reloaded")
    return finalized


async def materialize_and_finalize_for_scheduler(
    session: AsyncSession,
    *,
    user: User,
    target_date: date,
    now_utc: datetime | None = None,
) -> DailyCard:
    """Ensure a card exists for a scheduled date and finalize it once due.

    This is the callable seam for the later APScheduler phase.  It deliberately exists
    now so the no-entry-card rule is implemented in the domain service rather than in
    scheduler-specific code.  The scheduler will decide which ACTIVE devotees/dates to
    process and will provide PostgreSQL-backed locking; this function owns card
    materialization, snapshots, and deadline finalization.
    """

    profile, organization = await _load_devotee_context(session, user=user)
    now = now_utc or utc_now()
    today = organization_local_date(organization.timezone, now_utc=now)
    if target_date > today:
        raise DailyCardValidationError("Future daily cards cannot be materialized")

    if user.approved_at is not None:
        approved_local_date = to_organization_time(
            user.approved_at, organization.timezone
        ).date()
        if target_date < approved_local_date:
            raise DailyCardNotFoundError("No daily card exists before account approval")

    card = await _load_card(
        session,
        profile_id=profile.id,
        card_date=target_date,
    )
    if card is None:
        card = await _create_card(
            session,
            user=user,
            profile=profile,
            organization=organization,
            target_date=target_date,
        )
    return await _finalize_if_due(session, card=card, now_utc=now)


async def get_daily_card(
    session: AsyncSession,
    *,
    user: User,
    target_date: date | None = None,
    now_utc: datetime | None = None,
) -> DailyCard:
    profile, organization = await _load_devotee_context(session, user=user)
    now = now_utc or utc_now()
    today = organization_local_date(organization.timezone, now_utc=now)
    requested_date = target_date or today

    if requested_date > today:
        raise DailyCardValidationError("Future daily cards cannot be opened")

    if user.approved_at is not None:
        approved_local_date = to_organization_time(
            user.approved_at, organization.timezone
        ).date()
        if requested_date < approved_local_date:
            raise DailyCardNotFoundError("No daily card exists before account approval")

    card = await _load_card(
        session,
        profile_id=profile.id,
        card_date=requested_date,
    )

    if card is None:
        if requested_date != today:
            raise DailyCardNotFoundError(
                "Historical daily card not found. Missing-day cards are created by the automatic finalizer."
            )
        card = await _create_card(
            session,
            user=user,
            profile=profile,
            organization=organization,
            target_date=requested_date,
        )

    return await _finalize_if_due(session, card=card, now_utc=now)


async def update_today_card(
    session: AsyncSession,
    *,
    user: User,
    payload: DailyCardUpdateRequest,
    now_utc: datetime | None = None,
) -> DailyCard:
    profile, organization = await _load_devotee_context(session, user=user)
    now = now_utc or utc_now()
    today = organization_local_date(organization.timezone, now_utc=now)
    card = await _load_card(session, profile_id=profile.id, card_date=today)
    if card is None:
        card = await _create_card(
            session,
            user=user,
            profile=profile,
            organization=organization,
            target_date=today,
        )

    card = await _finalize_if_due(session, card=card, now_utc=now)
    if card.status != CardStatus.IN_PROGRESS or now >= card.deadline_at_utc:
        raise DailyCardNotEditableError(
            "Today's card is finalized and can no longer be edited by the devotee"
        )

    entries_by_activity = {entry.activity_id: entry for entry in card.activity_entries}
    touched_entries: set[uuid.UUID] = set()

    for activity_update in payload.activities:
        entry = entries_by_activity.get(activity_update.activity_id)
        if entry is None:
            raise DailyCardValidationError(
                "Activity is not applicable to this devotee's card"
            )
        if (
            entry.category_activity_config.scoring_type == ScoringType.SYSTEM_DERIVED
            or entry.activity.is_system_derived
        ):
            raise DailyCardValidationError(
                f"{entry.activity.name} is system-derived and cannot be edited"
            )

        values_by_field = {value.activity_field_id: value for value in entry.values}
        for value_update in activity_update.values:
            value = values_by_field.get(value_update.field_id)
            if value is None:
                raise DailyCardValidationError(
                    "Field does not belong to the supplied activity on this card"
                )
            field = value.activity_field
            # Membership in ``entry.values`` is the card-time snapshot. A field that
            # is archived later remains editable on this already-created card until
            # the card deadline; future cards simply will not snapshot it.
            _validate_typed_update(field, value_update)
            _apply_value_update(value, value_update, now)
        touched_entries.add(entry.id)

    for entry in card.activity_entries:
        if entry.id in touched_entries:
            entry.is_filled = _recompute_entry_completion(entry)

    # DAILY rules are deterministic and may be recomputed on every successful Update.
    # Weekly-aggregated/non-scored activities keep daily_score=NULL, and the system-derived
    # filling-card score remains NULL until auto-finalization.
    _apply_daily_scores(
        card,
        calculated_at=now,
        include_system_derived=False,
    )

    if card.first_update_at is None:
        card.first_update_at = now
    card.last_update_at = now
    card.revision_number += 1

    await session.commit()
    updated = await _load_card(session, profile_id=profile.id, card_date=today)
    if updated is None:
        raise DailyCardError("Updated daily card could not be reloaded")
    return updated


def serialize_daily_card(
    card: DailyCard,
    *,
    organization: Organization,
    now_utc: datetime | None = None,
) -> DailyCardPublic:
    now = now_utc or utc_now()
    today = organization_local_date(organization.timezone, now_utc=now)
    editable = (
        card.status == CardStatus.IN_PROGRESS
        and card.card_date == today
        and now < card.deadline_at_utc
    )

    activities: list[DailyActivityPublic] = []
    for entry in card.activity_entries:
        values = sorted(
            entry.values,
            key=lambda value: (
                value.activity_field.display_order,
                value.activity_field.field_key,
            ),
        )
        activities.append(
            DailyActivityPublic(
                entry_id=entry.id,
                activity_id=entry.activity_id,
                code=entry.activity.code,
                name=entry.activity.name,
                category=entry.activity.category,
                scoring_type=entry.category_activity_config.scoring_type,
                weekly_aggregation=entry.category_activity_config.weekly_aggregation,
                is_system_derived=entry.activity.is_system_derived,
                counts_toward_card_fill=entry.category_activity_config.counts_toward_card_fill,
                is_filled=entry.is_filled,
                daily_score=entry.daily_score,
                max_score_snapshot=entry.max_score_snapshot,
                score_calculated_at=entry.score_calculated_at,
                score_details=entry.score_details,
                values=[
                    DailyActivityValuePublic(
                        field_id=value.activity_field_id,
                        field_key=value.activity_field.field_key,
                        label=value.activity_field.label,
                        input_type=value.activity_field.input_type,
                        unit_code=value.activity_field.unit_code,
                        display_order=value.activity_field.display_order,
                        required_for_completion=value.activity_field.required_for_completion,
                        is_filled=value.is_filled,
                        numeric_value=value.numeric_value,
                        time_value=value.time_value,
                        boolean_value=value.boolean_value,
                        text_value=value.text_value,
                    )
                    for value in values
                ],
            )
        )

    activities.sort(
        key=lambda item: (
            0 if item.category.value == "SADHANA" else 1,
            next(
                entry.activity.created_at
                for entry in card.activity_entries
                if entry.activity_id == item.activity_id
            ),
            item.code,
        )
    )

    return DailyCardPublic(
        id=card.id,
        card_date=card.card_date,
        status=card.status,
        editable=editable,
        category_code=card.category_snapshot.code,
        category_name=card.category_snapshot.display_name,
        first_update_at=card.first_update_at,
        last_update_at=card.last_update_at,
        finalized_at=card.finalized_at,
        timezone_snapshot=card.timezone_snapshot,
        deadline_time_snapshot=card.deadline_time_snapshot,
        deadline_at_utc=card.deadline_at_utc,
        revision_number=card.revision_number,
        activities=activities,
    )


async def get_card_public(
    session: AsyncSession,
    *,
    user: User,
    target_date: date | None = None,
    now_utc: datetime | None = None,
) -> DailyCardPublic:
    card = await get_daily_card(
        session,
        user=user,
        target_date=target_date,
        now_utc=now_utc,
    )
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise DailyCardNotFoundError("Organization not found")
    return serialize_daily_card(card, organization=organization, now_utc=now_utc)


async def update_card_public(
    session: AsyncSession,
    *,
    user: User,
    payload: DailyCardUpdateRequest,
    now_utc: datetime | None = None,
) -> DailyCardPublic:
    card = await update_today_card(
        session,
        user=user,
        payload=payload,
        now_utc=now_utc,
    )
    organization = await session.get(Organization, user.organization_id)
    if organization is None:
        raise DailyCardNotFoundError("Organization not found")
    return serialize_daily_card(card, organization=organization, now_utc=now_utc)
