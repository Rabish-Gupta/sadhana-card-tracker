from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import AccountStatus, ChangeSource, RegistrationSource, UserRole
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timezone import get_week_bounds, organization_local_date
from app.models.devotee import DevoteeCategory, DevoteeCategoryHistory, DevoteeProfile
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import LoginRequest, RegistrationRequest


class AuthError(ValueError):
    pass


class DuplicateEmailError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class AccountNotActiveError(AuthError):
    def __init__(self, status: AccountStatus):
        self.status = status
        super().__init__(f"Account is not active: {status.value}")


class ConfigurationError(RuntimeError):
    pass


async def _get_default_organization(session: AsyncSession) -> Organization:
    result = await session.execute(
        select(Organization).where(
            Organization.code == settings.default_organization_code,
            Organization.is_active.is_(True),
        )
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        raise ConfigurationError(
            f"Active organization {settings.default_organization_code!r} is not configured"
        )
    return organization


async def _find_student_category(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    academic_year: int,
) -> DevoteeCategory:
    result = await session.execute(
        select(DevoteeCategory).where(
            DevoteeCategory.organization_id == organization_id,
            DevoteeCategory.academic_year == academic_year,
            DevoteeCategory.is_active.is_(True),
            DevoteeCategory.is_archived.is_(False),
        )
    )
    categories = list(result.scalars().all())
    if len(categories) != 1:
        raise ConfigurationError(
            "Exactly one active devotee category must be configured for "
            f"academic year {academic_year}; found {len(categories)}"
        )
    return categories[0]


async def register_devotee(
    session: AsyncSession,
    payload: RegistrationRequest,
) -> User:
    organization = await _get_default_organization(session)

    existing = await session.execute(
        select(User.id).where(
            User.organization_id == organization.id,
            User.email == str(payload.email),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateEmailError("An account with this email already exists")

    category = await _find_student_category(
        session,
        organization_id=organization.id,
        academic_year=payload.current_academic_year,
    )

    user = User(
        organization_id=organization.id,
        full_name=payload.full_name,
        email=str(payload.email),
        phone_number=payload.phone_number,
        password_hash=hash_password(payload.password),
        role=UserRole.DEVOTEE,
        account_status=AccountStatus.PENDING,
        registration_source=RegistrationSource.SELF_REGISTERED,
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

    local_date = organization_local_date(organization.timezone)
    effective_from_week, _ = get_week_bounds(local_date, organization.week_start_day)
    session.add(
        DevoteeCategoryHistory(
            devotee_profile_id=profile.id,
            previous_category_id=None,
            new_category_id=category.id,
            effective_from_week=effective_from_week,
            change_source=ChangeSource.SYSTEM,
            reason="Initial category assigned from academic year during self-registration",
            changed_by_id=None,
        )
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise DuplicateEmailError("An account with this email already exists") from exc

    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    payload: LoginRequest,
) -> tuple[User, str, int]:
    result = await session.execute(
        select(User).where(User.email == str(payload.email)).options(selectinload(User.organization))
    )
    users = result.scalars().all()
    # In the current MVP there is one default organization. Keeping organization-scoped
    # uniqueness in the DB leaves room for explicit organization selection later.
    user = next(
        (
            candidate
            for candidate in users
            if candidate.organization.code == settings.default_organization_code
        ),
        None,
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentialsError("Invalid email or password")
    if user.is_archived or user.account_status != AccountStatus.ACTIVE:
        raise AccountNotActiveError(user.account_status)

    token, expires_in = create_access_token(
        subject=str(user.id),
        organization_id=str(user.organization_id),
    )
    return user, token, expires_in


async def get_user_with_profile(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.devotee_profile).selectinload(DevoteeProfile.current_category),
        )
    )
    return result.scalar_one_or_none()
