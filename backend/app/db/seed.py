"""Idempotent baseline database seeder.

Run Alembic first, then execute this module. It seeds the approved v2.0 baseline as
normal configurable records; no scoring rule is hard-coded into application code.

A creator Admin is required because configuration records intentionally keep a
non-null created_by_id audit reference. For a fresh database the caller supplies a
bootstrap Admin password; the seeder hashes it with Argon2 before storage. Existing
Admins are never silently overwritten. An explicit reset flag is required to replace
an existing Admin password.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AccountStatus,
    RegistrationSource,
    RoundingMode,
    UserRole,
    VersionStatus,
    Weekday,
)
from app.core.security import hash_password, password_hash_is_valid_argon2
from app.core.timezone import get_week_bounds, organization_local_date
from app.db.seed_data import ACTIVITY_SEEDS, CATEGORY_SEEDS
from app.db.session import get_session_factory
from app.models.activity import Activity, ActivityField
from app.models.devotee import DevoteeCategory
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import Standard, StandardVersion
from app.models.user import User
from app.services.configuration import (
    require_week_boundary,
    validate_category_activity_config,
)


class SeedConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedOptions:
    organization_name: str = "VOICE"
    organization_code: str = "VOICE"
    timezone_name: str = "Asia/Kolkata"
    week_start_day: int = int(Weekday.MONDAY)
    daily_finalize_time: time = time(22, 0)
    promotion_month: int = 6
    effective_week: date | None = None
    admin_email: str = ""
    admin_full_name: str | None = None
    admin_phone: str | None = None
    admin_password: str | None = None
    reset_admin_password: bool = False


async def _scalar_one_or_none(session: AsyncSession, statement):
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def _get_or_create_organization(
    session: AsyncSession,
    options: SeedOptions,
) -> Organization:
    organization = await _scalar_one_or_none(
        session,
        select(Organization).where(Organization.code == options.organization_code),
    )
    if organization is not None:
        expected = {
            "timezone": options.timezone_name,
            "week_start_day": options.week_start_day,
            "daily_finalize_time": options.daily_finalize_time,
            "promotion_month": options.promotion_month,
        }
        differences = {
            key: (getattr(organization, key), value)
            for key, value in expected.items()
            if getattr(organization, key) != value
        }
        if differences:
            raise SeedConflictError(
                "Existing organization settings differ from requested seed settings: "
                f"{differences}. The seeder will not overwrite configured organization data."
            )
        return organization

    organization = Organization(
        name=options.organization_name,
        code=options.organization_code,
        timezone=options.timezone_name,
        week_start_day=options.week_start_day,
        daily_finalize_time=options.daily_finalize_time,
        promotion_month=options.promotion_month,
        is_active=True,
    )
    session.add(organization)
    await session.flush()
    return organization


async def _get_or_create_admin(
    session: AsyncSession,
    organization: Organization,
    options: SeedOptions,
) -> User:
    if not options.admin_email:
        raise SeedConflictError(
            "--admin-email is required because seeded configuration must have a creator Admin"
        )

    admin = await _scalar_one_or_none(
        session,
        select(User).where(
            User.organization_id == organization.id,
            User.email == options.admin_email,
        ),
    )
    if admin is not None:
        if admin.role != UserRole.ADMIN:
            raise SeedConflictError("The supplied existing user is not an ADMIN")
        if admin.account_status != AccountStatus.ACTIVE or admin.is_archived:
            raise SeedConflictError("The supplied existing Admin must be active and not archived")

        if not password_hash_is_valid_argon2(admin.password_hash):
            if not (options.reset_admin_password and options.admin_password):
                raise SeedConflictError(
                    "Existing Admin password_hash is not a valid Argon2 hash. "
                    "Rerun the seed with --admin-password and --reset-admin-password "
                    "to repair this bootstrap account explicitly."
                )

        if options.reset_admin_password:
            if not options.admin_password:
                raise SeedConflictError(
                    "--reset-admin-password requires --admin-password"
                )
            admin.password_hash = hash_password(options.admin_password)
            await session.flush()
        return admin

    missing = [
        name
        for name, value in {
            "admin_full_name": options.admin_full_name,
            "admin_phone": options.admin_phone,
            "admin_password": options.admin_password,
        }.items()
        if not value
    ]
    if missing:
        raise SeedConflictError(
            "Admin does not exist. Fresh bootstrap requires: " + ", ".join(missing)
        )

    admin = User(
        organization_id=organization.id,
        full_name=options.admin_full_name,
        email=options.admin_email,
        phone_number=options.admin_phone,
        password_hash=hash_password(options.admin_password),
        role=UserRole.ADMIN,
        account_status=AccountStatus.ACTIVE,
        registration_source=RegistrationSource.ADMIN_CREATED,
        approved_at=datetime.now(timezone.utc),
        is_archived=False,
    )
    session.add(admin)
    await session.flush()
    return admin


async def _ensure_organization_setting_baseline(
    session: AsyncSession,
    organization: Organization,
    admin: User,
    effective_week: date,
) -> OrganizationSettingVersion:
    versions = list(
        (
            await session.execute(
                select(OrganizationSettingVersion).where(
                    OrganizationSettingVersion.organization_id == organization.id
                )
            )
        ).scalars()
    )
    active = [item for item in versions if item.status == VersionStatus.ACTIVE]
    if len(active) > 1:
        raise SeedConflictError(
            "Organization has multiple ACTIVE settings versions; repair configuration before seeding"
        )

    expected = {
        "timezone": organization.timezone,
        "week_start_day": organization.week_start_day,
        "daily_finalize_time": organization.daily_finalize_time,
        "promotion_month": organization.promotion_month,
    }
    if active:
        current = active[0]
        differences = {
            key: (getattr(current, key), value)
            for key, value in expected.items()
            if getattr(current, key) != value
        }
        if differences:
            raise SeedConflictError(
                "ACTIVE organization settings version does not match organizations row: "
                f"{differences}"
            )
        return current

    if versions:
        raise SeedConflictError(
            "Organization settings history exists but no ACTIVE version is present"
        )

    version = OrganizationSettingVersion(
        organization_id=organization.id,
        version_number=1,
        effective_from_week=effective_week,
        status=VersionStatus.ACTIVE,
        created_by_id=admin.id,
        **expected,
    )
    session.add(version)
    await session.flush()
    return version


async def _seed_categories(
    session: AsyncSession,
    organization: Organization,
) -> dict[str, DevoteeCategory]:
    categories: dict[str, DevoteeCategory] = {}
    for spec in CATEGORY_SEEDS:
        category = await _scalar_one_or_none(
            session,
            select(DevoteeCategory).where(
                DevoteeCategory.organization_id == organization.id,
                DevoteeCategory.code == spec.code,
            ),
        )
        if category is None:
            category = DevoteeCategory(
                organization_id=organization.id,
                code=spec.code,
                display_name=spec.display_name,
                academic_year=spec.academic_year,
                stage_order=spec.stage_order,
                employment_status=spec.employment_status,
                is_active=True,
                is_archived=False,
            )
            session.add(category)
            await session.flush()
        else:
            semantic_values = {
                "display_name": spec.display_name,
                "academic_year": spec.academic_year,
                "stage_order": spec.stage_order,
                "employment_status": spec.employment_status,
            }
            differences = {
                key: (getattr(category, key), expected)
                for key, expected in semantic_values.items()
                if getattr(category, key) != expected
            }
            if differences:
                raise SeedConflictError(
                    f"Existing category {spec.code} has incompatible semantics: {differences}. "
                    "The seeder will not silently redefine historical devotee categories."
                )
        categories[spec.code] = category
    return categories


async def _seed_activity(
    session: AsyncSession,
    organization: Organization,
    spec,
) -> Activity:
    activity = await _scalar_one_or_none(
        session,
        select(Activity).where(
            Activity.organization_id == organization.id,
            Activity.code == spec.code,
        ),
    )
    if activity is None:
        activity = Activity(
            organization_id=organization.id,
            code=spec.code,
            name=spec.name,
            category=spec.category,
            description=spec.description,
            is_system_derived=spec.is_system_derived,
            is_active=True,
            is_archived=False,
        )
        session.add(activity)
        await session.flush()
    else:
        if activity.category != spec.category or activity.is_system_derived != spec.is_system_derived:
            raise SeedConflictError(
                f"Existing activity {spec.code} has incompatible semantics; "
                "historical activity meanings are never silently overwritten"
            )

    for field_spec in spec.fields:
        field = await _scalar_one_or_none(
            session,
            select(ActivityField).where(
                ActivityField.activity_id == activity.id,
                ActivityField.field_key == field_spec.key,
            ),
        )
        if field is None:
            session.add(
                ActivityField(
                    activity_id=activity.id,
                    field_key=field_spec.key,
                    label=field_spec.label,
                    input_type=field_spec.input_type,
                    unit_code=field_spec.unit_code,
                    display_order=field_spec.display_order,
                    required_for_completion=field_spec.required_for_completion,
                    is_active=True,
                    is_archived=False,
                )
            )
        else:
            semantic_tuple = (field.input_type, field.unit_code)
            requested_tuple = (field_spec.input_type, field_spec.unit_code)
            if semantic_tuple != requested_tuple:
                raise SeedConflictError(
                    f"Existing field {spec.code}.{field_spec.key} has different semantic type/unit; "
                    "archive and replace historically used fields instead of mutating them"
                )
    await session.flush()
    return activity


async def _seed_rule(
    session: AsyncSession,
    organization: Organization,
    admin: User,
    activity: Activity,
    spec,
    effective_week: date,
) -> ScoringRule | None:
    if spec.rule is None:
        return None

    rule = await _scalar_one_or_none(
        session,
        select(ScoringRule).where(
            ScoringRule.organization_id == organization.id,
            ScoringRule.activity_id == activity.id,
            ScoringRule.name == spec.rule.name,
        ),
    )
    if rule is None:
        rule = ScoringRule(
            organization_id=organization.id,
            activity_id=activity.id,
            name=spec.rule.name,
            rule_type=spec.rule.rule_type,
            is_active=True,
            is_archived=False,
            created_by_id=admin.id,
        )
        session.add(rule)
        await session.flush()
    elif rule.rule_type != spec.rule.rule_type:
        raise SeedConflictError(f"Existing rule {spec.rule.name} has a different rule type")

    version = await _scalar_one_or_none(
        session,
        select(ScoringRuleVersion).where(
            ScoringRuleVersion.scoring_rule_id == rule.id,
            ScoringRuleVersion.version_number == 1,
        ),
    )
    if version is None:
        session.add(
            ScoringRuleVersion(
                scoring_rule_id=rule.id,
                version_number=1,
                effective_from_week=effective_week,
                status=VersionStatus.ACTIVE,
                max_score=spec.rule.max_score,
                rounding_mode=RoundingMode.HALF_UP,
                configuration=spec.rule.configuration,
                created_by_id=admin.id,
            )
        )
    else:
        if version.effective_from_week != effective_week:
            raise SeedConflictError(
                f"Existing baseline rule version for {activity.code} uses another effective week"
            )
        if version.max_score != spec.rule.max_score or version.configuration != spec.rule.configuration:
            raise SeedConflictError(
                f"Existing baseline rule version for {activity.code} differs from the approved seed"
            )
    await session.flush()
    return rule


async def _seed_standard(
    session: AsyncSession,
    organization: Organization,
    admin: User,
    activity: Activity,
    spec,
    effective_week: date,
) -> Standard | None:
    if spec.standard is None:
        return None

    standard = await _scalar_one_or_none(
        session,
        select(Standard).where(
            Standard.organization_id == organization.id,
            Standard.activity_id == activity.id,
            Standard.name == spec.standard.name,
        ),
    )
    if standard is None:
        standard = Standard(
            organization_id=organization.id,
            activity_id=activity.id,
            name=spec.standard.name,
            is_active=True,
            is_archived=False,
            created_by_id=admin.id,
        )
        session.add(standard)
        await session.flush()

    version = await _scalar_one_or_none(
        session,
        select(StandardVersion).where(
            StandardVersion.standard_id == standard.id,
            StandardVersion.version_number == 1,
        ),
    )
    if version is None:
        session.add(
            StandardVersion(
                standard_id=standard.id,
                version_number=1,
                effective_from_week=effective_week,
                period=spec.standard.period,
                target_definition=spec.standard.target_definition,
                status=VersionStatus.ACTIVE,
                created_by_id=admin.id,
            )
        )
    else:
        if version.effective_from_week != effective_week:
            raise SeedConflictError(
                f"Existing baseline standard version for {activity.code} uses another effective week"
            )
        if (
            version.period != spec.standard.period
            or version.target_definition != spec.standard.target_definition
        ):
            raise SeedConflictError(
                f"Existing baseline standard version for {activity.code} differs from the approved seed"
            )
    await session.flush()
    return standard


async def _seed_category_configs(
    session: AsyncSession,
    organization: Organization,
    admin: User,
    categories: dict[str, DevoteeCategory],
    activity: Activity,
    spec,
    rule: ScoringRule | None,
    standard: Standard | None,
    effective_week: date,
) -> None:
    for category in categories.values():
        config = await _scalar_one_or_none(
            session,
            select(CategoryActivityConfig).where(
                CategoryActivityConfig.category_id == category.id,
                CategoryActivityConfig.activity_id == activity.id,
                CategoryActivityConfig.version_number == 1,
            ),
        )
        if config is not None:
            expected_rule_id = rule.id if rule else None
            expected_standard_id = standard.id if standard else None
            if config.effective_from_week != effective_week:
                raise SeedConflictError(
                    f"Existing baseline config for {category.code}/{activity.code} "
                    "uses another effective week"
                )
            if (
                config.scoring_type != spec.scoring_type
                or config.weekly_aggregation != spec.weekly_aggregation
                or config.scoring_rule_id != expected_rule_id
                or config.standard_id != expected_standard_id
                or config.counts_toward_card_fill != spec.counts_toward_card_fill
            ):
                raise SeedConflictError(
                    f"Existing baseline config for {category.code}/{activity.code} "
                    "differs from the approved seed"
                )
            continue

        config = CategoryActivityConfig(
            organization_id=organization.id,
            category_id=category.id,
            activity_id=activity.id,
            version_number=1,
            effective_from_week=effective_week,
            is_applicable=True,
            scoring_type=spec.scoring_type,
            weekly_aggregation=spec.weekly_aggregation,
            scoring_rule_id=rule.id if rule else None,
            standard_id=standard.id if standard else None,
            counts_toward_card_fill=spec.counts_toward_card_fill,
            status=VersionStatus.ACTIVE,
            created_by_id=admin.id,
        )
        validate_category_activity_config(
            config,
            scoring_rule=rule,
            standard=standard,
        )
        session.add(config)
    await session.flush()


async def seed_initial_data(session: AsyncSession, options: SeedOptions) -> dict[str, int | str]:
    """Seed the shared baseline profile in one transaction.

    Existing records are reused. Semantic mismatches raise instead of being overwritten,
    protecting the project's historical-immutability principle.
    """

    async with session.begin():
        organization = await _get_or_create_organization(session, options)
        admin = await _get_or_create_admin(session, organization, options)
        categories = await _seed_categories(session, organization)

        if options.effective_week is None:
            local_date = organization_local_date(organization.timezone)
            effective_week, _ = get_week_bounds(local_date, organization.week_start_day)
        else:
            effective_week = options.effective_week
        require_week_boundary(effective_week, organization.week_start_day)
        await _ensure_organization_setting_baseline(
            session, organization, admin, effective_week
        )

        activity_count = 0
        rule_count = 0
        standard_count = 0
        config_count = 0

        for spec in ACTIVITY_SEEDS:
            activity = await _seed_activity(session, organization, spec)
            rule = await _seed_rule(
                session,
                organization,
                admin,
                activity,
                spec,
                effective_week,
            )
            standard = await _seed_standard(
                session,
                organization,
                admin,
                activity,
                spec,
                effective_week,
            )
            await _seed_category_configs(
                session,
                organization,
                admin,
                categories,
                activity,
                spec,
                rule,
                standard,
                effective_week,
            )
            activity_count += 1
            rule_count += int(rule is not None)
            standard_count += int(standard is not None)
            config_count += len(categories)

        return {
            "organization_code": organization.code,
            "effective_week": effective_week.isoformat(),
            "categories": len(categories),
            "activities": activity_count,
            "rules": rule_count,
            "standards": standard_count,
            "category_activity_configs": config_count,
            "organization_setting_versions": 1,
        }


def _parse_args() -> SeedOptions:
    parser = argparse.ArgumentParser(description="Seed Sadhana Card Tracker baseline data")
    parser.add_argument("--organization-name", default="VOICE")
    parser.add_argument("--organization-code", default="VOICE")
    parser.add_argument("--timezone", default="Asia/Kolkata", dest="timezone_name")
    parser.add_argument("--effective-week", type=date.fromisoformat, default=None)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-full-name")
    parser.add_argument("--admin-phone")
    parser.add_argument(
        "--admin-password",
        help=(
            "Bootstrap Admin plaintext password. It is Argon2-hashed immediately before "
            "storage. For local development, prefer entering it only on a trusted machine."
        ),
    )
    parser.add_argument(
        "--reset-admin-password",
        action="store_true",
        help=(
            "Explicitly replace an existing Admin password with --admin-password. "
            "Required to repair legacy/test bootstrap hashes; never happens silently."
        ),
    )
    args = parser.parse_args()
    return SeedOptions(
        organization_name=args.organization_name,
        organization_code=args.organization_code,
        timezone_name=args.timezone_name,
        effective_week=args.effective_week,
        admin_email=args.admin_email,
        admin_full_name=args.admin_full_name,
        admin_phone=args.admin_phone,
        admin_password=args.admin_password,
        reset_admin_password=args.reset_admin_password,
    )


async def _async_main() -> None:
    options = _parse_args()
    async with get_session_factory()() as session:
        result = await seed_initial_data(session, options)
    print("Seed complete:")
    for key, value in result.items():
        print(f"  {key}: {value}")


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
