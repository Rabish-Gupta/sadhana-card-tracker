from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import AccountStatus, CardStatus, UserRole, VersionStatus
from app.core.timezone import get_week_bounds, get_zoneinfo, local_deadline_to_utc, organization_local_date, utc_now
from app.db.session import get_engine, get_session_factory
from app.models.audit import AuditLog
from app.models.daily_card import DailyCard
from app.models.devotee import DevoteeProfile
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.evaluation_config import CategoryActivityConfig
from app.models.user import User
from app.models.weekly_evaluation import WeeklyEvaluation
from app.services.configuration_admin import activate_due_configuration
from app.services.daily_cards import (
    _resolve_setting_version_for_date,
    materialize_and_finalize_for_scheduler,
)
from app.services.lifecycle import (
    apply_due_category_transitions,
    apply_due_deactivations,
    reconcile_automatic_promotions,
    reconcile_pending_academic_lifecycle,
)
from app.services.weekly_evaluations import (
    PartialLifecycleWeekError,
    WeeklyEvaluationNotReadyError,
    generate_weekly_evaluation,
)

logger = logging.getLogger(__name__)


class SchedulerError(RuntimeError):
    pass


def advisory_lock_key(organization_id: uuid.UUID) -> int:
    """Stable signed BIGINT key for PostgreSQL session advisory locking."""

    digest = hashlib.blake2b(
        b"sadhana-card-tracker:lifecycle:v1:" + organization_id.bytes,
        digest_size=8,
    ).digest()
    unsigned = int.from_bytes(digest, "big", signed=False)
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def account_active_at(
    *,
    approved_at: datetime | None,
    lifecycle_events: list[tuple[str, datetime]],
    instant: datetime,
) -> bool:
    """Reconstruct account activity at an instant from approval + audited state changes."""

    if approved_at is None or approved_at > instant:
        return False
    active = True
    for action, occurred_at in sorted(lifecycle_events, key=lambda item: item[1]):
        if occurred_at > instant:
            break
        if action == "ACCOUNT_DEACTIVATED":
            active = False
        elif action == "ACCOUNT_ACTIVATED":
            active = True
    return active


async def _lifecycle_events_for_user(
    session: AsyncSession, *, user: User
) -> list[tuple[str, datetime]]:
    result = await session.execute(
        select(AuditLog.action, AuditLog.created_at)
        .where(
            AuditLog.organization_id == user.organization_id,
            AuditLog.entity_type == "USER",
            AuditLog.entity_id == user.id,
            AuditLog.action.in_(["ACCOUNT_DEACTIVATED", "ACCOUNT_ACTIVATED"]),
        )
        .order_by(AuditLog.created_at)
    )
    return [(action, created_at) for action, created_at in result.all()]




async def _organization_history_floor(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> date | None:
    """Earliest date for which automated historical materialization is safe.

    Step 11 can be introduced into a database that already contains devotees whose
    approval/category history predates the first versioned organization/settings and
    category/activity configuration snapshots.  Those pre-configuration dates cannot
    be reconstructed deterministically, so scheduler catch-up must never invent cards
    for them.

    The floor is the later of the first organization-settings version and the first
    category/activity configuration version.  Existing persisted cards earlier than
    this floor are still finalized from their own snapshots; the floor applies only to
    *missing-card backfill* and generated weekly evaluations.
    """

    settings_floor = await session.scalar(
        select(func.min(OrganizationSettingVersion.effective_from_week)).where(
            OrganizationSettingVersion.organization_id == organization_id,
            OrganizationSettingVersion.status.in_(
                [VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
        )
    )
    config_floor = await session.scalar(
        select(func.min(CategoryActivityConfig.effective_from_week)).where(
            CategoryActivityConfig.organization_id == organization_id,
            CategoryActivityConfig.status.in_(
                [VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
        )
    )
    if settings_floor is None or config_floor is None:
        return None
    return max(settings_floor, config_floor)

async def _process_due_cards(
    session: AsyncSession,
    *,
    organization: Organization,
    now_utc: datetime,
) -> int:
    """Finalize existing due cards and backfill every missing due card for active instants."""

    changed = 0
    history_floor = await _organization_history_floor(
        session, organization_id=organization.id
    )
    # Existing cards must finalize even if the account has since become inactive.
    due_result = await session.execute(
        select(DailyCard, User)
        .join(DevoteeProfile, DevoteeProfile.id == DailyCard.devotee_profile_id)
        .join(User, User.id == DevoteeProfile.user_id)
        .where(
            DailyCard.organization_id == organization.id,
            DailyCard.status == CardStatus.IN_PROGRESS,
            DailyCard.deadline_at_utc <= now_utc,
        )
    )
    for card, user in due_result.all():
        before = card.status
        finalized = await materialize_and_finalize_for_scheduler(
            session, user=user, target_date=card.card_date, now_utc=now_utc
        )
        if before != finalized.status:
            changed += 1

    # Backfill missing no-entry cards. This deliberately considers both currently ACTIVE
    # and INACTIVE devotees, reconstructing whether they were active at each day's deadline.
    # If versioned configuration has no historical baseline yet, existing cards can still
    # finalize, but missing historical cards cannot be reconstructed safely.
    if history_floor is None:
        return changed

    users_result = await session.execute(
        select(User)
        .where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.account_status.in_([AccountStatus.ACTIVE, AccountStatus.INACTIVE]),
            User.approved_at.is_not(None),
            User.is_archived.is_(False),
        )
        .options(selectinload(User.devotee_profile))
    )
    local_today = organization_local_date(organization.timezone, now_utc=now_utc)
    for user in users_result.scalars().all():
        if user.devotee_profile is None or user.approved_at is None:
            continue
        events = await _lifecycle_events_for_user(session, user=user)
        approved_local = user.approved_at.astimezone(get_zoneinfo(organization.timezone)).date()
        existing_result = await session.execute(
            select(DailyCard.card_date).where(
                DailyCard.devotee_profile_id == user.devotee_profile.id,
                DailyCard.card_date >= max(approved_local, history_floor),
                DailyCard.card_date <= local_today,
            )
        )
        existing_dates = set(existing_result.scalars().all())
        day = max(approved_local, history_floor)
        while day <= local_today:
            if day not in existing_dates:
                setting = await _resolve_setting_version_for_date(
                    session,
                    organization_id=organization.id,
                    target_date=day,
                )
                deadline_utc = local_deadline_to_utc(
                    day, setting.daily_finalize_time, setting.timezone
                )
                if deadline_utc <= now_utc and account_active_at(
                    approved_at=user.approved_at,
                    lifecycle_events=events,
                    instant=deadline_utc,
                ):
                    await materialize_and_finalize_for_scheduler(
                        session, user=user, target_date=day, now_utc=now_utc
                    )
                    changed += 1
            day += timedelta(days=1)
    return changed


async def _completed_week_candidates(
    session: AsyncSession,
    *,
    organization: Organization,
    earliest_date: date,
    now_utc: datetime,
) -> list[date]:
    settings_result = await session.execute(
        select(OrganizationSettingVersion)
        .where(
            OrganizationSettingVersion.organization_id == organization.id,
            OrganizationSettingVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
        )
        .order_by(OrganizationSettingVersion.effective_from_week)
    )
    versions = list(settings_result.scalars().all())
    if not versions:
        return []
    current_local = organization_local_date(organization.timezone, now_utc=now_utc)
    candidates: set[date] = set()
    day = earliest_date
    while day <= current_local:
        eligible = [v for v in versions if v.effective_from_week <= day]
        if not eligible:
            day += timedelta(days=1)
            continue
        setting = eligible[-1]
        week_start, week_end = get_week_bounds(day, setting.week_start_day)
        # A week-start-setting change may define an effective boundary that is not
        # canonical under the new numbering; include that boundary explicitly.
        if setting.effective_from_week <= day <= setting.effective_from_week + timedelta(days=6):
            week_start = setting.effective_from_week
            week_end = week_start + timedelta(days=6)
        if organization_local_date(setting.timezone, now_utc=now_utc) > week_end:
            candidates.add(week_start)
        day += timedelta(days=1)
    return sorted(candidates)


async def _process_weekly_evaluations(
    session: AsyncSession,
    *,
    organization: Organization,
    now_utc: datetime,
) -> tuple[int, int]:
    users_result = await session.execute(
        select(User)
        .where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.approved_at.is_not(None),
            User.is_archived.is_(False),
            User.account_status.in_([AccountStatus.ACTIVE, AccountStatus.INACTIVE]),
        )
        .options(selectinload(User.devotee_profile))
    )
    users = [user for user in users_result.scalars().all() if user.devotee_profile is not None]
    if not users:
        return 0, 0
    history_floor = await _organization_history_floor(
        session, organization_id=organization.id
    )
    if history_floor is None:
        return 0, 0
    earliest = max(
        history_floor,
        min(
        user.approved_at.astimezone(get_zoneinfo(organization.timezone)).date()
            for user in users
            if user.approved_at is not None
        ),
    )
    weeks = await _completed_week_candidates(
        session, organization=organization, earliest_date=earliest, now_utc=now_utc
    )
    generated = 0
    skipped_partial = 0
    for user in users:
        profile = user.devotee_profile
        assert profile is not None
        existing_result = await session.execute(
            select(WeeklyEvaluation.week_start_date).where(
                WeeklyEvaluation.devotee_profile_id == profile.id
            )
        )
        existing = set(existing_result.scalars().all())
        for week_start in weeks:
            if week_start in existing:
                continue
            try:
                await generate_weekly_evaluation(
                    session, user=user, week_start=week_start, now_utc=now_utc
                )
                generated += 1
            except PartialLifecycleWeekError:
                skipped_partial += 1
            except WeeklyEvaluationNotReadyError:
                continue
    return generated, skipped_partial


async def run_organization_lifecycle(
    organization_id: uuid.UUID,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Run one idempotent organization lifecycle pass under a PostgreSQL advisory lock."""

    now = now_utc or utc_now()
    engine = get_engine()
    lock_key = advisory_lock_key(organization_id)
    session_factory = get_session_factory()

    # Keep the session-level advisory lock on a dedicated PostgreSQL connection, while
    # lifecycle work uses the normal session factory on its own connection(s). Binding the
    # AsyncSession to the same connection that executed pg_try_advisory_lock caused that
    # connection to already be inside SQLAlchemy's implicit outer transaction. Service-level
    # session.commit() calls then did not commit that outer transaction, so the lifecycle pass
    # could report work (for example, materialized cards) that was rolled back when the lock
    # connection closed. A separate lock connection preserves the cross-process mutex without
    # swallowing domain-service commits.
    async with engine.connect() as lock_connection:
        acquired = bool(
            await lock_connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
            )
        )
        # End SQLAlchemy's implicit transaction created by the SELECT. PostgreSQL session-level
        # advisory locks survive COMMIT and remain held until pg_advisory_unlock/connection close.
        await lock_connection.commit()
        if not acquired:
            return {"organization_id": organization_id, "lock_acquired": False}

        try:
            async with session_factory() as session:
                organization = await session.get(Organization, organization_id)
                if organization is None or not organization.is_active:
                    return {"organization_id": organization_id, "lock_acquired": True, "inactive": True}

                pre_local_today = organization_local_date(organization.timezone, now_utc=now)
                pre_week_start, _ = get_week_bounds(pre_local_today, organization.week_start_day)
                configuration = await activate_due_configuration(
                    session,
                    organization_id=organization_id,
                    actor_user_id=None,
                    now_utc=now,
                )
                # Activation may have changed timezone/week-start/promotion month. The old
                # boundary is still honored for transitions already scheduled under the old
                # definition, while new automatic promotions use the newly active boundary.
                await session.refresh(organization)
                local_today = organization_local_date(organization.timezone, now_utc=now)
                current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
                transition_boundary = max(pre_week_start, current_week_start)

                rescheduled = await reconcile_pending_academic_lifecycle(
                    session,
                    organization=organization,
                    current_week_start=current_week_start,
                    now_utc=now,
                )
                scheduled = await reconcile_automatic_promotions(
                    session,
                    organization=organization,
                    current_week_start=current_week_start,
                    now_utc=now,
                )
                applied = await apply_due_category_transitions(
                    session,
                    organization=organization,
                    current_week_start=transition_boundary,
                    now_utc=now,
                )
                deactivated = await apply_due_deactivations(
                    session,
                    organization=organization,
                    current_week_start=transition_boundary,
                    now_utc=now,
                )
                history_floor = await _organization_history_floor(
                    session, organization_id=organization.id
                )
                cards = await _process_due_cards(
                    session, organization=organization, now_utc=now
                )
                weekly_generated, weekly_skipped = await _process_weekly_evaluations(
                    session, organization=organization, now_utc=now
                )
                return {
                    "organization_id": organization_id,
                    "lock_acquired": True,
                    "configuration_activated": configuration,
                    "pending_academic_lifecycle_rescheduled": rescheduled,
                    "automatic_promotions_scheduled": scheduled,
                    "category_transitions_applied": applied,
                    "deactivations_applied": deactivated,
                    "history_floor": history_floor,
                    "cards_materialized_or_finalized": cards,
                    "weekly_evaluations_generated": weekly_generated,
                    "weekly_evaluations_skipped_partial": weekly_skipped,
                }
        finally:
            try:
                await lock_connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
                )
                await lock_connection.commit()
            except Exception:
                logger.exception("Failed to release lifecycle advisory lock for %s", organization_id)


async def run_scheduler_tick(*, now_utc: datetime | None = None) -> list[dict[str, Any]]:
    now = now_utc or utc_now()
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Organization.id).where(Organization.is_active.is_(True)).order_by(Organization.code)
        )
        organization_ids = list(result.scalars().all())
    results: list[dict[str, Any]] = []
    for organization_id in organization_ids:
        try:
            results.append(
                await run_organization_lifecycle(organization_id, now_utc=now)
            )
        except Exception:
            logger.exception("Lifecycle scheduler failed for organization %s", organization_id)
    return results


def start_lifecycle_scheduler():
    """Create/start APScheduler lazily so importing the API does not require it."""

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except ImportError as exc:  # pragma: no cover - local install supplies runtime dependency
        raise SchedulerError(
            "APScheduler is required for Step 11 automation; run pip install -e '.[dev]'"
        ) from exc

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_scheduler_tick,
        trigger="interval",
        seconds=max(10, settings.scheduler_interval_seconds),
        id="sadhana-lifecycle-tick",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=max(60, settings.scheduler_interval_seconds * 3),
    )
    scheduler.start()
    return scheduler
