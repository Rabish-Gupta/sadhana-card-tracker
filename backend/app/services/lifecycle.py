from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AccountStatus, ChangeSource, EmploymentStatus, UserRole, VersionStatus
from app.core.timezone import get_week_bounds, get_zoneinfo, organization_local_date, utc_now
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.user import User
from app.schemas.lifecycle import (
    LifecycleStatusPublic,
    PendingCategoryTransitionPublic,
    SahadevaReviewItem,
    SahadevaReviewResult,
)
from app.services.audit import add_audit_log


class LifecycleError(ValueError):
    pass


class LifecycleNotFoundError(LifecycleError):
    pass


class LifecycleConflictError(LifecycleError):
    pass


class LifecycleValidationError(LifecycleError):
    pass


def first_week_start_on_or_after(year: int, month: int, week_start_day: int) -> date:
    """Return the first organization week boundary on/after the first day of month."""

    first = date(year, month, 1)
    start, _ = get_week_bounds(first, week_start_day)
    return start if start == first else start + timedelta(days=7)


def promotion_boundary_for_profile(
    profile: DevoteeProfile,
    category: DevoteeCategory,
    organization: Organization,
) -> date | None:
    """Resolve the next stage's normal academic promotion boundary.

    A student's nth academic year transitions after year n, so the boundary year is
    ``college_joining_year + n``. Bhima categories have no academic year and therefore
    no automatic academic promotion boundary.
    """

    if category.academic_year is None:
        return None
    year = profile.college_joining_year + category.academic_year
    return first_week_start_on_or_after(year, organization.promotion_month, organization.week_start_day)


def local_week_start_utc(week_start: date, timezone_name: str) -> datetime:
    return datetime.combine(week_start, time.min, tzinfo=get_zoneinfo(timezone_name)).astimezone(timezone.utc)


async def _load_user_profile_org(
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
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or user.devotee_profile is None:
        raise LifecycleNotFoundError("Devotee not found")
    organization = await session.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise LifecycleNotFoundError("Organization not found or inactive")
    return user, user.devotee_profile, organization


async def _category_by_code(
    session: AsyncSession, *, organization_id: uuid.UUID, code: str
) -> DevoteeCategory:
    category = await session.scalar(
        select(DevoteeCategory).where(
            DevoteeCategory.organization_id == organization_id,
            DevoteeCategory.code == code,
            DevoteeCategory.is_active.is_(True),
            DevoteeCategory.is_archived.is_(False),
        )
    )
    if category is None:
        raise LifecycleValidationError(f"Required category is unavailable: {code}")
    return category


async def _pending_category_transition(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    current_week_start: date,
) -> DevoteeCategoryHistory | None:
    result = await session.execute(
        select(DevoteeCategoryHistory)
        .where(
            DevoteeCategoryHistory.devotee_profile_id == profile_id,
            DevoteeCategoryHistory.effective_from_week > current_week_start,
        )
        .options(selectinload(DevoteeCategoryHistory.new_category))
        .order_by(DevoteeCategoryHistory.effective_from_week)
    )
    rows = list(result.scalars().all())
    if len(rows) > 1:
        raise LifecycleConflictError(
            "More than one future category transition exists; Admin correction is required"
        )
    return rows[0] if rows else None


async def _schedule_category_transition(
    session: AsyncSession,
    *,
    user: User,
    profile: DevoteeProfile,
    organization: Organization,
    target_category: DevoteeCategory,
    effective_week: date,
    source: ChangeSource,
    actor_user_id: uuid.UUID | None,
    reason: str,
    now_utc: datetime,
    allow_current_week: bool = False,
) -> DevoteeCategoryHistory:
    current_week_start, _ = get_week_bounds(
        organization_local_date(organization.timezone, now_utc=now_utc),
        organization.week_start_day,
    )
    canonical, _ = get_week_bounds(effective_week, organization.week_start_day)
    if canonical != effective_week:
        raise LifecycleValidationError("Category transition must be effective on a week boundary")
    minimum = current_week_start if allow_current_week else current_week_start + timedelta(days=7)
    if effective_week < minimum:
        raise LifecycleConflictError(
            f"Category transition cannot be effective before {minimum.isoformat()}"
        )
    if target_category.id == profile.current_category_id:
        raise LifecycleConflictError("Target category is already current")

    same_week = await session.scalar(
        select(DevoteeCategoryHistory).where(
            DevoteeCategoryHistory.devotee_profile_id == profile.id,
            DevoteeCategoryHistory.effective_from_week == effective_week,
        )
    )
    pending = await _pending_category_transition(
        session,
        profile_id=profile.id,
        current_week_start=current_week_start,
    )

    row = same_week or pending
    before = None
    if row is None:
        row = DevoteeCategoryHistory(
            devotee_profile_id=profile.id,
            previous_category_id=profile.current_category_id,
            new_category_id=target_category.id,
            effective_from_week=effective_week,
            change_source=source,
            reason=reason,
            changed_by_id=actor_user_id,
            created_at=now_utc,
        )
        session.add(row)
        await session.flush()
    else:
        if row.effective_from_week <= current_week_start and not allow_current_week:
            raise LifecycleConflictError("An effective category transition cannot be edited")
        before = {
            "target_category_id": row.new_category_id,
            "effective_from_week": row.effective_from_week,
            "change_source": row.change_source,
            "reason": row.reason,
        }
        row.previous_category_id = profile.current_category_id
        row.new_category_id = target_category.id
        # Keep the already-loaded ORM relationship synchronized with the FK.
        # Without this assignment, revising a pending transition in the same
        # AsyncSession can return the previous target from SQLAlchemy's identity
        # map even though ``new_category_id`` has been updated correctly.
        row.new_category = target_category
        row.effective_from_week = effective_week
        row.change_source = source
        row.reason = reason
        row.changed_by_id = actor_user_id

    await add_audit_log(
        session,
        organization_id=user.organization_id,
        actor_user_id=actor_user_id,
        entity_type="DEVOTEE_CATEGORY_HISTORY",
        entity_id=row.id,
        action="CATEGORY_TRANSITION_SCHEDULED" if before is None else "CATEGORY_TRANSITION_RESCHEDULED",
        reason=reason,
        before_data=before,
        after_data={
            "previous_category_id": profile.current_category_id,
            "target_category_id": target_category.id,
            "effective_from_week": effective_week,
            "change_source": source,
        },
    )
    return row


async def _remove_future_category_transition(
    session: AsyncSession,
    *,
    user: User,
    profile: DevoteeProfile,
    organization: Organization,
    actor_user_id: uuid.UUID | None,
    reason: str,
    now_utc: datetime,
) -> None:
    current_week_start, _ = get_week_bounds(
        organization_local_date(organization.timezone, now_utc=now_utc),
        organization.week_start_day,
    )
    pending = await _pending_category_transition(
        session, profile_id=profile.id, current_week_start=current_week_start
    )
    if pending is None:
        return
    await add_audit_log(
        session,
        organization_id=user.organization_id,
        actor_user_id=actor_user_id,
        entity_type="DEVOTEE_CATEGORY_HISTORY",
        entity_id=pending.id,
        action="CATEGORY_TRANSITION_CANCELLED",
        reason=reason,
        before_data={
            "target_category_id": pending.new_category_id,
            "effective_from_week": pending.effective_from_week,
        },
    )
    await session.delete(pending)


async def get_lifecycle_status(
    session: AsyncSession,
    *,
    user: User,
    now_utc: datetime | None = None,
) -> LifecycleStatusPublic:
    loaded, profile, organization = await _load_user_profile_org(
        session, organization_id=user.organization_id, user_id=user.id
    )
    now = now_utc or utc_now()
    local_today = organization_local_date(organization.timezone, now_utc=now)
    current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
    pending = await _pending_category_transition(
        session, profile_id=profile.id, current_week_start=current_week_start
    )
    boundary = promotion_boundary_for_profile(profile, profile.current_category, organization)
    sahadeva_due = profile.current_category.code == "SAHADEVA" and boundary is not None and current_week_start >= boundary
    bhima_choice_required = (
        profile.current_category.code == "YUDHISHTHIRA"
        and boundary is not None
        and current_week_start >= boundary
        and pending is None
    )
    return LifecycleStatusPublic(
        current_category_code=profile.current_category.code,
        current_category_name=profile.current_category.display_name,
        current_academic_year=profile.current_academic_year,
        next_promotion_week=boundary,
        sahadeva_review_due=sahadeva_due,
        bhima_choice_required=bhima_choice_required,
        pending_category_transition=(
            PendingCategoryTransitionPublic(
                history_id=pending.id,
                target_category_code=pending.new_category.code,
                target_category_name=pending.new_category.display_name,
                effective_from_week=pending.effective_from_week,
                change_source=pending.change_source,
                reason=pending.reason,
            )
            if pending is not None
            else None
        ),
        pending_deactivation_week=loaded.pending_deactivation_week,
        pending_deactivation_reason=loaded.pending_deactivation_reason,
    )


async def list_sahadeva_reviews(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    include_not_due: bool = False,
    now_utc: datetime | None = None,
) -> list[SahadevaReviewItem]:
    organization = await session.get(Organization, organization_id)
    if organization is None:
        raise LifecycleNotFoundError("Organization not found")
    now = now_utc or utc_now()
    local_today = organization_local_date(organization.timezone, now_utc=now)
    current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
    result = await session.execute(
        select(User)
        .join(DevoteeProfile, DevoteeProfile.user_id == User.id)
        .join(DevoteeCategory, DevoteeCategory.id == DevoteeProfile.current_category_id)
        .where(
            User.organization_id == organization_id,
            User.role == UserRole.DEVOTEE,
            User.account_status == AccountStatus.ACTIVE,
            User.is_archived.is_(False),
            DevoteeCategory.code == "SAHADEVA",
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
        .order_by(User.full_name)
    )
    items: list[SahadevaReviewItem] = []
    for user in result.scalars().all():
        profile = user.devotee_profile
        if profile is None:
            continue
        due_week = promotion_boundary_for_profile(profile, profile.current_category, organization)
        if due_week is None:
            continue
        due = current_week_start >= due_week
        if not include_not_due and not due:
            continue
        pending = await _pending_category_transition(
            session, profile_id=profile.id, current_week_start=current_week_start
        )
        decision: Literal["CONTINUE_TO_NAKULA", "DEACTIVATE"] | None = None
        effective: date | None = None
        if user.pending_deactivation_week is not None:
            decision = "DEACTIVATE"
            effective = user.pending_deactivation_week
        elif pending is not None and pending.new_category.code == "NAKULA":
            decision = "CONTINUE_TO_NAKULA"
            effective = pending.effective_from_week
        items.append(
            SahadevaReviewItem(
                user_id=user.id,
                full_name=user.full_name,
                email=str(user.email),
                due_week=due_week,
                review_due=due,
                pending_decision=decision,
                pending_effective_week=effective,
            )
        )
    return items


async def schedule_sahadeva_review(
    session: AsyncSession,
    *,
    admin: User,
    devotee_user_id: uuid.UUID,
    decision: Literal["CONTINUE_TO_NAKULA", "DEACTIVATE"],
    reason: str,
    now_utc: datetime | None = None,
) -> SahadevaReviewResult:
    user, profile, organization = await _load_user_profile_org(
        session, organization_id=admin.organization_id, user_id=devotee_user_id
    )
    if user.account_status != AccountStatus.ACTIVE:
        raise LifecycleConflictError("Sahadeva review requires an active devotee account")
    if profile.current_category.code != "SAHADEVA":
        raise LifecycleConflictError("Sahadeva review is only valid for the SAHADEVA category")

    now = now_utc or utc_now()
    local_today = organization_local_date(organization.timezone, now_utc=now)
    current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
    boundary = promotion_boundary_for_profile(profile, profile.current_category, organization)
    if boundary is None:
        raise LifecycleValidationError("Sahadeva promotion boundary could not be determined")
    effective = boundary if boundary > current_week_start else current_week_start + timedelta(days=7)

    if decision == "CONTINUE_TO_NAKULA":
        target = await _category_by_code(
            session, organization_id=organization.id, code="NAKULA"
        )
        user.pending_deactivation_week = None
        user.pending_deactivation_reason = None
        user.pending_deactivation_requested_by_id = None
        user.pending_deactivation_scheduled_at = None
        await _schedule_category_transition(
            session,
            user=user,
            profile=profile,
            organization=organization,
            target_category=target,
            effective_week=effective,
            source=ChangeSource.ADMIN,
            actor_user_id=admin.id,
            reason=reason,
            now_utc=now,
        )
        action = "SAHADEVA_CONTINUATION_SCHEDULED"
    else:
        await _remove_future_category_transition(
            session,
            user=user,
            profile=profile,
            organization=organization,
            actor_user_id=admin.id,
            reason="Sahadeva review changed to deactivation",
            now_utc=now,
        )
        user.pending_deactivation_week = effective
        user.pending_deactivation_reason = reason
        user.pending_deactivation_requested_by_id = admin.id
        user.pending_deactivation_scheduled_at = now
        action = "SAHADEVA_DEACTIVATION_SCHEDULED"

    await add_audit_log(
        session,
        organization_id=organization.id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action=action,
        reason=reason,
        after_data={"decision": decision, "effective_from_week": effective},
    )
    await session.commit()
    return SahadevaReviewResult(
        user_id=user.id,
        decision=decision,
        effective_from_week=effective,
        scheduled_at=now,
    )


async def request_bhima_status(
    session: AsyncSession,
    *,
    devotee: User,
    employment_status: EmploymentStatus,
    reason: str,
    now_utc: datetime | None = None,
) -> LifecycleStatusPublic:
    user, profile, organization = await _load_user_profile_org(
        session, organization_id=devotee.organization_id, user_id=devotee.id
    )
    if user.account_status != AccountStatus.ACTIVE:
        raise LifecycleConflictError("Only active devotees may schedule a Bhima status change")
    current_code = profile.current_category.code
    if current_code not in {"YUDHISHTHIRA", "BHIMA_WORKING", "BHIMA_NOT_WORKING"}:
        raise LifecycleConflictError(
            "Bhima status may only be chosen by Yudhishthira or changed by a Bhima devotee"
        )
    target_code = "BHIMA_WORKING" if employment_status == EmploymentStatus.WORKING else "BHIMA_NOT_WORKING"

    now = now_utc or utc_now()
    local_today = organization_local_date(organization.timezone, now_utc=now)
    current_week_start, _ = get_week_bounds(local_today, organization.week_start_day)
    pending = await _pending_category_transition(
        session, profile_id=profile.id, current_week_start=current_week_start
    )
    if current_code == target_code:
        # An existing Bhima may change their mind before next week. Selecting the
        # currently-active status cancels the pending opposite-status transition.
        if current_code in {"BHIMA_WORKING", "BHIMA_NOT_WORKING"} and pending is not None:
            await _remove_future_category_transition(
                session,
                user=user,
                profile=profile,
                organization=organization,
                actor_user_id=user.id,
                reason=reason,
                now_utc=now,
            )
            await session.commit()
            return await get_lifecycle_status(session, user=user, now_utc=now)
        raise LifecycleConflictError("Requested Bhima status is already current")

    if current_code == "YUDHISHTHIRA":
        boundary = promotion_boundary_for_profile(profile, profile.current_category, organization)
        if boundary is None:
            raise LifecycleValidationError("Graduation boundary could not be determined")
        effective = boundary if boundary > current_week_start else current_week_start + timedelta(days=7)
    else:
        effective = current_week_start + timedelta(days=7)

    target = await _category_by_code(
        session, organization_id=organization.id, code=target_code
    )
    await _schedule_category_transition(
        session,
        user=user,
        profile=profile,
        organization=organization,
        target_category=target,
        effective_week=effective,
        source=ChangeSource.DEVOTEE,
        actor_user_id=user.id,
        reason=reason,
        now_utc=now,
    )
    await session.commit()
    return await get_lifecycle_status(session, user=user, now_utc=now)


async def reconcile_pending_academic_lifecycle(
    session: AsyncSession,
    *,
    organization: Organization,
    current_week_start: date,
    now_utc: datetime,
) -> int:
    """Keep not-yet-effective academic transitions aligned with active promotion settings.

    A future Sahadeva review decision or Yudhishthira Bhima choice may be made months
    before graduation. If Admin later changes ``promotion_month`` before that transition
    becomes effective, the pending lifecycle date follows the newly ACTIVE setting.
    Bhima Working <-> Not Working changes are intentionally excluded because those are
    always next-week changes, not academic-promotion changes.
    """

    result = await session.execute(
        select(User)
        .join(DevoteeProfile, DevoteeProfile.user_id == User.id)
        .join(DevoteeCategory, DevoteeCategory.id == DevoteeProfile.current_category_id)
        .where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.account_status == AccountStatus.ACTIVE,
            User.is_archived.is_(False),
            DevoteeCategory.code.in_(["SAHADEVA", "YUDHISHTHIRA"]),
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
    )
    changed = 0
    for user in result.scalars().all():
        profile = user.devotee_profile
        if profile is None:
            continue
        boundary = promotion_boundary_for_profile(profile, profile.current_category, organization)
        if boundary is None:
            continue
        desired = boundary if boundary > current_week_start else current_week_start + timedelta(days=7)
        pending = await _pending_category_transition(
            session, profile_id=profile.id, current_week_start=current_week_start
        )

        if profile.current_category.code == "SAHADEVA":
            if user.pending_deactivation_week is not None and user.pending_deactivation_week > current_week_start:
                if user.pending_deactivation_week != desired:
                    before = user.pending_deactivation_week
                    user.pending_deactivation_week = desired
                    await add_audit_log(
                        session,
                        organization_id=organization.id,
                        actor_user_id=None,
                        entity_type="USER",
                        entity_id=user.id,
                        action="SAHADEVA_DEACTIVATION_RESCHEDULED_BY_SETTINGS",
                        before_data={"effective_from_week": before},
                        after_data={"effective_from_week": desired},
                    )
                    changed += 1
            elif pending is not None and pending.new_category.code == "NAKULA" and pending.effective_from_week != desired:
                before = pending.effective_from_week
                pending.effective_from_week = desired
                await add_audit_log(
                    session,
                    organization_id=organization.id,
                    actor_user_id=None,
                    entity_type="DEVOTEE_CATEGORY_HISTORY",
                    entity_id=pending.id,
                    action="CATEGORY_TRANSITION_RESCHEDULED_BY_SETTINGS",
                    before_data={"effective_from_week": before},
                    after_data={"effective_from_week": desired, "target_category": "NAKULA"},
                )
                changed += 1

        elif (
            profile.current_category.code == "YUDHISHTHIRA"
            and pending is not None
            and pending.new_category.code in {"BHIMA_WORKING", "BHIMA_NOT_WORKING"}
            and pending.effective_from_week != desired
        ):
            before = pending.effective_from_week
            pending.effective_from_week = desired
            await add_audit_log(
                session,
                organization_id=organization.id,
                actor_user_id=None,
                entity_type="DEVOTEE_CATEGORY_HISTORY",
                entity_id=pending.id,
                action="CATEGORY_TRANSITION_RESCHEDULED_BY_SETTINGS",
                before_data={"effective_from_week": before},
                after_data={
                    "effective_from_week": desired,
                    "target_category": pending.new_category.code,
                },
            )
            changed += 1

    if changed:
        await session.commit()
    return changed


async def reconcile_automatic_promotions(
    session: AsyncSession,
    *,
    organization: Organization,
    current_week_start: date,
    now_utc: datetime,
) -> int:
    """Schedule due Nakula→Arjuna and Arjuna→Yudhishthira promotions.

    Sahadeva requires Admin review, and Yudhishthira requires the devotee's explicit
    initial Bhima status choice, so neither is auto-promoted here.
    """

    result = await session.execute(
        select(User)
        .join(DevoteeProfile, DevoteeProfile.user_id == User.id)
        .join(DevoteeCategory, DevoteeCategory.id == DevoteeProfile.current_category_id)
        .where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.account_status == AccountStatus.ACTIVE,
            User.is_archived.is_(False),
            DevoteeCategory.code.in_(["NAKULA", "ARJUNA"]),
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
    )
    target_by_code = {
        "NAKULA": "ARJUNA",
        "ARJUNA": "YUDHISHTHIRA",
    }
    scheduled = 0
    for user in result.scalars().all():
        profile = user.devotee_profile
        if profile is None:
            continue
        boundary = promotion_boundary_for_profile(profile, profile.current_category, organization)
        if boundary is None or current_week_start < boundary:
            continue
        existing_this_week = await session.scalar(
            select(DevoteeCategoryHistory).where(
                DevoteeCategoryHistory.devotee_profile_id == profile.id,
                DevoteeCategoryHistory.effective_from_week == current_week_start,
            )
        )
        if existing_this_week is not None:
            continue
        target_code = target_by_code[profile.current_category.code]
        target = await _category_by_code(
            session, organization_id=organization.id, code=target_code
        )
        await _schedule_category_transition(
            session,
            user=user,
            profile=profile,
            organization=organization,
            target_category=target,
            effective_week=current_week_start,
            source=ChangeSource.SYSTEM,
            actor_user_id=None,
            reason=f"Automatic academic promotion {profile.current_category.code} → {target_code}",
            now_utc=now_utc,
            allow_current_week=True,
        )
        scheduled += 1
    await session.commit()
    return scheduled


async def apply_due_category_transitions(
    session: AsyncSession,
    *,
    organization: Organization,
    current_week_start: date,
    now_utc: datetime,
) -> int:
    profiles_result = await session.execute(
        select(DevoteeProfile)
        .join(User, User.id == DevoteeProfile.user_id)
        .where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.is_archived.is_(False),
        )
        .options(selectinload(DevoteeProfile.current_category), selectinload(DevoteeProfile.user))
    )
    applied = 0
    for profile in profiles_result.scalars().all():
        history = await session.scalar(
            select(DevoteeCategoryHistory)
            .where(
                DevoteeCategoryHistory.devotee_profile_id == profile.id,
                DevoteeCategoryHistory.effective_from_week <= current_week_start,
            )
            .options(selectinload(DevoteeCategoryHistory.new_category))
            .order_by(DevoteeCategoryHistory.effective_from_week.desc())
            .limit(1)
        )
        if history is None or history.new_category_id == profile.current_category_id:
            continue
        previous = profile.current_category
        profile.current_category_id = history.new_category_id
        profile.current_category = history.new_category
        profile.current_academic_year = history.new_category.academic_year
        await add_audit_log(
            session,
            organization_id=organization.id,
            actor_user_id=None,
            entity_type="DEVOTEE_PROFILE",
            entity_id=profile.id,
            action="CATEGORY_TRANSITION_APPLIED",
            reason=history.reason,
            before_data={
                "category": previous.code,
                "current_academic_year": previous.academic_year,
            },
            after_data={
                "category": history.new_category.code,
                "current_academic_year": history.new_category.academic_year,
                "effective_from_week": history.effective_from_week,
            },
            created_at=now_utc,
        )
        applied += 1
    await session.commit()
    return applied


async def apply_due_deactivations(
    session: AsyncSession,
    *,
    organization: Organization,
    current_week_start: date,
    now_utc: datetime,
) -> int:
    result = await session.execute(
        select(User).where(
            User.organization_id == organization.id,
            User.role == UserRole.DEVOTEE,
            User.account_status == AccountStatus.ACTIVE,
            User.pending_deactivation_week.is_not(None),
            User.pending_deactivation_week <= current_week_start,
        )
    )
    count = 0
    for user in result.scalars().all():
        effective_week = user.pending_deactivation_week
        reason = user.pending_deactivation_reason or "Scheduled lifecycle deactivation"
        requested_by = user.pending_deactivation_requested_by_id
        setting = await session.scalar(
            select(OrganizationSettingVersion)
            .where(
                OrganizationSettingVersion.organization_id == organization.id,
                OrganizationSettingVersion.status.in_([VersionStatus.ACTIVE, VersionStatus.ARCHIVED]),
                OrganizationSettingVersion.effective_from_week <= (effective_week or current_week_start),
            )
            .order_by(OrganizationSettingVersion.effective_from_week.desc())
            .limit(1)
        )
        timezone_name = setting.timezone if setting is not None else organization.timezone
        effective_at = local_week_start_utc(effective_week or current_week_start, timezone_name)
        user.account_status = AccountStatus.INACTIVE
        user.deactivated_at = effective_at
        user.pending_deactivation_week = None
        user.pending_deactivation_reason = None
        user.pending_deactivation_requested_by_id = None
        user.pending_deactivation_scheduled_at = None
        await add_audit_log(
            session,
            organization_id=organization.id,
            actor_user_id=requested_by,
            entity_type="USER",
            entity_id=user.id,
            action="ACCOUNT_DEACTIVATED",
            reason=reason,
            before_data={"account_status": AccountStatus.ACTIVE},
            after_data={"account_status": AccountStatus.INACTIVE, "effective_week": effective_week},
            created_at=effective_at,
        )
        count += 1
    await session.commit()
    return count
