from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    AccountStatus,
    ChangeSource,
    RegistrationSource,
    UserRole,
)
from app.core.security import hash_password
from app.core.timezone import get_week_bounds, organization_local_date, utc_now
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.organization import Organization
from app.models.user import User
from app.schemas.admin import AdminCreateDevoteeRequest
from app.services.audit import add_audit_log


class UserManagementError(ValueError):
    pass


class UserNotFoundError(UserManagementError):
    pass


class InvalidAccountTransitionError(UserManagementError):
    pass


class DuplicateEmailError(UserManagementError):
    pass


class CategoryValidationError(UserManagementError):
    pass


async def _load_devotee(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
) -> User:
    result = await session.execute(
        select(User)
        .where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.role == UserRole.DEVOTEE,
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError("Devotee not found")
    return user


async def _load_category(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    code: str,
) -> DevoteeCategory:
    result = await session.execute(
        select(DevoteeCategory).where(
            DevoteeCategory.organization_id == organization_id,
            DevoteeCategory.code == code,
            DevoteeCategory.is_active.is_(True),
            DevoteeCategory.is_archived.is_(False),
        )
    )
    category = result.scalar_one_or_none()
    if category is None:
        raise CategoryValidationError(f"Unknown or inactive category: {code}")
    return category


def _validate_academic_year(
    category: DevoteeCategory,
    current_academic_year: int | None,
) -> None:
    if category.academic_year is not None:
        if current_academic_year is None:
            raise CategoryValidationError(
                f"current_academic_year is required for {category.code}"
            )
        if current_academic_year != category.academic_year:
            raise CategoryValidationError(
                f"{category.code} requires academic year {category.academic_year}"
            )
    elif current_academic_year is not None:
        raise CategoryValidationError(
            f"current_academic_year must be omitted for {category.code}"
        )


async def list_devotees(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    account_status: AccountStatus | None = None,
) -> list[User]:
    statement = (
        select(User)
        .where(
            User.organization_id == organization_id,
            User.role == UserRole.DEVOTEE,
            User.is_archived.is_(False),
        )
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category)
        )
        .order_by(User.created_at.desc())
    )
    if account_status is not None:
        statement = statement.where(User.account_status == account_status)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def create_devotee_by_admin(
    session: AsyncSession,
    *,
    admin: User,
    payload: AdminCreateDevoteeRequest,
) -> User:
    existing = await session.execute(
        select(User.id).where(
            User.organization_id == admin.organization_id,
            User.email == str(payload.email),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateEmailError("An account with this email already exists")

    category = await _load_category(
        session,
        organization_id=admin.organization_id,
        code=payload.category_code,
    )
    _validate_academic_year(category, payload.current_academic_year)

    user = User(
        organization_id=admin.organization_id,
        full_name=payload.full_name,
        email=str(payload.email),
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role=UserRole.DEVOTEE,
        account_status=AccountStatus.ACTIVE,
        registration_source=RegistrationSource.ADMIN_CREATED,
        approved_by_id=admin.id,
        approved_at=utc_now(),
        is_archived=False,
    )
    session.add(user)
    await session.flush()

    profile = DevoteeProfile(
        user_id=user.id,
        current_category_id=category.id,
        college=payload.college,
        branch=payload.branch,
        college_joining_year=payload.college_joining_year,
        expected_graduation_year=payload.college_joining_year + 4,
        current_academic_year=payload.current_academic_year,
    )
    session.add(profile)
    await session.flush()

    organization = await session.get(Organization, admin.organization_id)
    if organization is None:
        raise UserManagementError("Organization not found")
    local_date = organization_local_date(organization.timezone)
    effective_from_week, _ = get_week_bounds(local_date, organization.week_start_day)
    session.add(
        DevoteeCategoryHistory(
            devotee_profile_id=profile.id,
            previous_category_id=None,
            new_category_id=category.id,
            effective_from_week=effective_from_week,
            change_source=ChangeSource.ADMIN,
            reason="Initial category assigned when Admin created devotee account",
            changed_by_id=admin.id,
        )
    )
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action="DEVOTEE_CREATED",
        after_data={
            "account_status": AccountStatus.ACTIVE,
            "category": category.code,
            "registration_source": RegistrationSource.ADMIN_CREATED,
        },
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEmailError("An account with this email already exists") from exc
    return await _load_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=user.id,
    )


async def approve_registration(
    session: AsyncSession,
    *,
    admin: User,
    user_id: uuid.UUID,
) -> User:
    user = await _load_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=user_id,
    )
    if user.account_status != AccountStatus.PENDING:
        raise InvalidAccountTransitionError("Only pending registrations can be approved")

    before = user.account_status
    user.account_status = AccountStatus.ACTIVE
    user.approved_by_id = admin.id
    user.approved_at = utc_now()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action="ACCOUNT_APPROVED",
        before_data={"account_status": before},
        after_data={"account_status": user.account_status},
    )
    await session.commit()
    return user


async def reject_registration(
    session: AsyncSession,
    *,
    admin: User,
    user_id: uuid.UUID,
    reason: str | None,
) -> User:
    user = await _load_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=user_id,
    )
    if user.account_status != AccountStatus.PENDING:
        raise InvalidAccountTransitionError("Only pending registrations can be rejected")

    before = user.account_status
    user.account_status = AccountStatus.REJECTED
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action="ACCOUNT_REJECTED",
        reason=reason.strip() if reason else None,
        before_data={"account_status": before},
        after_data={"account_status": user.account_status},
    )
    await session.commit()
    return user


async def deactivate_devotee(
    session: AsyncSession,
    *,
    admin: User,
    user_id: uuid.UUID,
    reason: str,
) -> User:
    user = await _load_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=user_id,
    )
    if user.account_status != AccountStatus.ACTIVE:
        raise InvalidAccountTransitionError("Only active accounts can be deactivated")

    before = user.account_status
    user.account_status = AccountStatus.INACTIVE
    user.deactivated_at = utc_now()
    user.pending_deactivation_week = None
    user.pending_deactivation_reason = None
    user.pending_deactivation_requested_by_id = None
    user.pending_deactivation_scheduled_at = None
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action="ACCOUNT_DEACTIVATED",
        reason=reason,
        before_data={"account_status": before},
        after_data={"account_status": user.account_status},
    )
    await session.commit()
    return user


async def activate_devotee(
    session: AsyncSession,
    *,
    admin: User,
    user_id: uuid.UUID,
    reason: str,
) -> User:
    user = await _load_devotee(
        session,
        organization_id=admin.organization_id,
        user_id=user_id,
    )
    if user.account_status != AccountStatus.INACTIVE:
        raise InvalidAccountTransitionError("Only inactive accounts can be reactivated")

    before = user.account_status
    user.account_status = AccountStatus.ACTIVE
    user.deactivated_at = None
    user.pending_deactivation_week = None
    user.pending_deactivation_reason = None
    user.pending_deactivation_requested_by_id = None
    user.pending_deactivation_scheduled_at = None
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="USER",
        entity_id=user.id,
        action="ACCOUNT_ACTIVATED",
        reason=reason,
        before_data={"account_status": before},
        after_data={"account_status": user.account_status},
    )
    await session.commit()
    return user
