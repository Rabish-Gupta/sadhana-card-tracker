from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ActivityInputType, RuleType, ScoringType, StandardPeriod, VersionStatus
from app.core.timezone import get_week_bounds, organization_local_date
from app.models.activity import Activity, ActivityField
from app.models.devotee import DevoteeCategory
from app.models.evaluation_config import CategoryActivityConfig
from app.models.organization import Organization
from app.models.organization_settings import OrganizationSettingVersion
from app.models.scoring import ScoringRule, ScoringRuleVersion
from app.models.standard import Standard, StandardVersion
from app.models.user import User
from app.schemas.configuration import (
    ActivityCreateRequest,
    ActivityFieldCreateRequest,
    ActivityFieldUpdateRequest,
    ActivityUpdateRequest,
    CategoryActivityConfigCreateRequest,
    CategoryActivityConfigUpdateRequest,
    ScoringRuleCreateRequest,
    ScoringRuleUpdateRequest,
    ScoringRuleVersionCreateRequest,
    ScoringRuleVersionUpdateRequest,
    StandardCreateRequest,
    StandardUpdateRequest,
    StandardVersionCreateRequest,
    StandardVersionUpdateRequest,
    OrganizationSettingVersionCreateRequest,
    OrganizationSettingVersionUpdateRequest,
)
from app.services.audit import add_audit_log
from app.services.scoring import ScoringConfigurationError, validate_rule_configuration
from app.services.configuration import (
    ConfigurationValidationError,
    require_week_boundary,
    standard_kind_input_type,
    validate_category_activity_config,
    validate_standard_target_definition,
)


class ConfigurationAdminError(ValueError):
    pass


class ConfigurationNotFoundError(ConfigurationAdminError):
    pass


class ConfigurationConflictError(ConfigurationAdminError):
    pass


class ImmutableVersionError(ConfigurationAdminError):
    pass


async def _get_org(session: AsyncSession, organization_id: uuid.UUID) -> Organization:
    org = await session.get(Organization, organization_id)
    if org is None or not org.is_active:
        raise ConfigurationNotFoundError("Organization not found or inactive")
    return org


def _next_week_start(org: Organization, *, today: date | None = None) -> date:
    local_today = today or organization_local_date(org.timezone)
    current_start, _ = get_week_bounds(local_today, org.week_start_day)
    return current_start + timedelta(days=7)


def _validate_pending_week(org: Organization, effective_from_week: date | None) -> date:
    target = effective_from_week or _next_week_start(org)
    require_week_boundary(target, org.week_start_day)
    minimum = _next_week_start(org)
    if target < minimum:
        raise ConfigurationConflictError(
            f"Pending configuration must become effective on or after {minimum.isoformat()}"
        )
    return target


def _validate_executable_rule_version(
    rule: ScoringRule,
    *,
    max_score: int,
    configuration: dict[str, Any],
) -> None:
    try:
        validate_rule_configuration(rule.rule_type, configuration, max_score)
    except ScoringConfigurationError as exc:
        raise ConfigurationAdminError(f"Invalid scoring configuration: {exc}") from exc


async def _validate_standard_version_definition(
    session: AsyncSession,
    *,
    standard: Standard,
    period: StandardPeriod,
    target_definition: dict[str, Any],
) -> None:
    """Reject standard JSON that the analysis engine cannot execute safely."""

    try:
        validate_standard_target_definition(period, target_definition)
    except ConfigurationValidationError as exc:
        raise ConfigurationAdminError(f"Invalid standard target: {exc}") from exc

    activity = await session.scalar(
        select(Activity)
        .options(selectinload(Activity.fields))
        .where(Activity.id == standard.activity_id)
    )
    if activity is None:
        raise ConfigurationNotFoundError("Standard activity not found")

    kind_type = standard_kind_input_type(target_definition)
    if activity.is_system_derived:
        if period != StandardPeriod.DAILY or kind_type != ActivityInputType.BOOLEAN:
            raise ConfigurationAdminError(
                "System-derived activity standards must be DAILY BOOLEAN targets"
            )
        if target_definition.get("field_key") is not None:
            raise ConfigurationAdminError(
                "System-derived activity standards cannot reference a raw field_key"
            )
        return

    fields = [field for field in activity.fields if field.is_active and not field.is_archived]
    candidates = [field for field in fields if field.input_type == kind_type]
    field_key = target_definition.get("field_key")
    if field_key is not None:
        candidates = [field for field in candidates if field.field_key == field_key]
    if len(candidates) != 1:
        raise ConfigurationAdminError(
            "Standard target must resolve to exactly one active activity field; "
            "supply field_key when the input type is ambiguous"
        )
    target_field = candidates[0]
    unit = target_definition.get("unit")
    if unit is not None:
        if target_field.unit_code is None or (
            str(unit).strip().upper() != target_field.unit_code.strip().upper()
        ):
            raise ConfigurationAdminError(
                f"Standard unit {unit!r} does not match field unit {target_field.unit_code!r}"
            )


async def _effective_rule_version_for_config(
    session: AsyncSession,
    *,
    rule_id: uuid.UUID,
    effective_week: date,
) -> ScoringRuleVersion | None:
    return await session.scalar(
        select(ScoringRuleVersion)
        .where(
            ScoringRuleVersion.scoring_rule_id == rule_id,
            ScoringRuleVersion.effective_from_week <= effective_week,
            ScoringRuleVersion.status.in_(
                [VersionStatus.PENDING, VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
        )
        .order_by(
            ScoringRuleVersion.effective_from_week.desc(),
            ScoringRuleVersion.version_number.desc(),
        )
        .limit(1)
    )


async def _effective_standard_version_for_config(
    session: AsyncSession,
    *,
    standard_id: uuid.UUID,
    effective_week: date,
) -> StandardVersion | None:
    return await session.scalar(
        select(StandardVersion)
        .where(
            StandardVersion.standard_id == standard_id,
            StandardVersion.effective_from_week <= effective_week,
            StandardVersion.status.in_(
                [VersionStatus.PENDING, VersionStatus.ACTIVE, VersionStatus.ARCHIVED]
            ),
        )
        .order_by(
            StandardVersion.effective_from_week.desc(),
            StandardVersion.version_number.desc(),
        )
        .limit(1)
    )


async def _preflight_category_config_activation(
    session: AsyncSession,
    *,
    config: CategoryActivityConfig,
) -> None:
    """Ensure an activating config has executable dependencies for its effective week."""

    rule = None
    if config.scoring_rule_id is not None:
        rule = await session.scalar(
            select(ScoringRule).where(
                ScoringRule.id == config.scoring_rule_id,
                ScoringRule.organization_id == config.organization_id,
                ScoringRule.is_archived.is_(False),
            )
        )
    standard = None
    if config.standard_id is not None:
        standard = await session.scalar(
            select(Standard).where(
                Standard.id == config.standard_id,
                Standard.organization_id == config.organization_id,
                Standard.is_archived.is_(False),
            )
        )
    try:
        validate_category_activity_config(config, scoring_rule=rule, standard=standard)
    except ConfigurationValidationError as exc:
        raise ConfigurationConflictError(str(exc)) from exc

    if not config.is_applicable:
        return

    rule_version = None
    if rule is not None:
        rule_version = await _effective_rule_version_for_config(
            session, rule_id=rule.id, effective_week=config.effective_from_week
        )
        if rule_version is None:
            raise ConfigurationConflictError(
                "Category/activity config has no scoring-rule version effective for its target week"
            )
        _validate_executable_rule_version(
            rule,
            max_score=rule_version.max_score,
            configuration=rule_version.configuration,
        )

    if config.scoring_type == ScoringType.DAILY:
        if rule is None or rule.rule_type not in {RuleType.BOOLEAN, RuleType.THRESHOLD}:
            raise ConfigurationConflictError(
                "DAILY configs currently require a BOOLEAN or THRESHOLD scoring rule"
            )
    elif config.scoring_type == ScoringType.SYSTEM_DERIVED:
        if rule is None or rule.rule_type != RuleType.SYSTEM_DERIVED:
            raise ConfigurationConflictError(
                "SYSTEM_DERIVED configs require a SYSTEM_DERIVED scoring rule"
            )
    elif config.scoring_type == ScoringType.WEEKLY_AGGREGATED:
        if rule is None or rule.rule_type != RuleType.PERCENTAGE:
            raise ConfigurationConflictError(
                "WEEKLY_AGGREGATED configs currently require a PERCENTAGE scoring rule"
            )
    elif config.scoring_type == ScoringType.NON_SCORED:
        if rule is not None or rule_version is not None:
            raise ConfigurationConflictError("NON_SCORED configs cannot resolve a scoring rule")

    standard_version = None
    if standard is not None:
        standard_version = await _effective_standard_version_for_config(
            session, standard_id=standard.id, effective_week=config.effective_from_week
        )
        if standard_version is None:
            raise ConfigurationConflictError(
                "Category/activity config has no standard version effective for its target week"
            )
        await _validate_standard_version_definition(
            session,
            standard=standard,
            period=standard_version.period,
            target_definition=standard_version.target_definition,
        )

    if rule is not None and rule.rule_type == RuleType.PERCENTAGE:
        if standard_version is None or standard_version.period != StandardPeriod.WEEKLY:
            raise ConfigurationConflictError(
                "PERCENTAGE weekly scoring requires an effective WEEKLY standard version"
            )


async def list_categories(session: AsyncSession, organization_id: uuid.UUID) -> list[DevoteeCategory]:
    result = await session.execute(
        select(DevoteeCategory)
        .where(DevoteeCategory.organization_id == organization_id)
        .order_by(DevoteeCategory.stage_order, DevoteeCategory.code)
    )
    return list(result.scalars())


async def list_activities(
    session: AsyncSession,
    organization_id: uuid.UUID,
    *,
    include_archived: bool = False,
) -> list[Activity]:
    stmt = (
        select(Activity)
        .options(selectinload(Activity.fields))
        .where(Activity.organization_id == organization_id)
        .order_by(Activity.category, Activity.name)
    )
    if not include_archived:
        stmt = stmt.where(Activity.is_archived.is_(False))
    result = await session.execute(stmt)
    return list(result.scalars().unique())


async def create_activity(
    session: AsyncSession,
    *,
    admin: User,
    payload: ActivityCreateRequest,
) -> Activity:
    existing = await session.scalar(
        select(Activity).where(
            Activity.organization_id == admin.organization_id,
            Activity.code == payload.code,
        )
    )
    if existing is not None:
        raise ConfigurationConflictError("Activity code already exists in this organization")
    activity = Activity(
        organization_id=admin.organization_id,
        code=payload.code,
        name=payload.name,
        category=payload.category,
        description=payload.description,
        is_system_derived=payload.is_system_derived,
        is_active=True,
        is_archived=False,
    )
    session.add(activity)
    await session.flush()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ACTIVITY",
        entity_id=activity.id,
        action="ACTIVITY_CREATED",
        after_data={"code": activity.code, "name": activity.name, "category": activity.category},
    )
    await session.commit()
    await session.refresh(activity)
    return activity


async def update_activity(
    session: AsyncSession,
    *,
    admin: User,
    activity_id: uuid.UUID,
    payload: ActivityUpdateRequest,
) -> Activity:
    activity = await session.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.organization_id == admin.organization_id,
        )
    )
    if activity is None:
        raise ConfigurationNotFoundError("Activity not found")
    if activity.is_archived:
        raise ConfigurationConflictError("Archived activity cannot be edited")
    before = {"name": activity.name, "description": activity.description}
    if payload.name is not None:
        activity.name = payload.name
    if "description" in payload.model_fields_set:
        activity.description = payload.description
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ACTIVITY",
        entity_id=activity.id,
        action="ACTIVITY_UPDATED",
        before_data=before,
        after_data={"name": activity.name, "description": activity.description},
    )
    await session.commit()
    await session.refresh(activity)
    return activity


async def archive_activity(
    session: AsyncSession,
    *,
    admin: User,
    activity_id: uuid.UUID,
    reason: str,
) -> Activity:
    activity = await session.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.organization_id == admin.organization_id,
        )
    )
    if activity is None:
        raise ConfigurationNotFoundError("Activity not found")
    if activity.is_archived:
        return activity
    activity.is_active = False
    activity.is_archived = True
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ACTIVITY",
        entity_id=activity.id,
        action="ACTIVITY_ARCHIVED",
        reason=reason,
        before_data={"is_active": True, "is_archived": False},
        after_data={"is_active": False, "is_archived": True},
    )
    await session.commit()
    await session.refresh(activity)
    return activity


async def create_activity_field(
    session: AsyncSession,
    *,
    admin: User,
    activity_id: uuid.UUID,
    payload: ActivityFieldCreateRequest,
) -> ActivityField:
    activity = await session.scalar(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.organization_id == admin.organization_id,
            Activity.is_archived.is_(False),
        )
    )
    if activity is None:
        raise ConfigurationNotFoundError("Activity not found")
    if activity.is_system_derived:
        raise ConfigurationConflictError("System-derived activities cannot have user input fields")
    existing = await session.scalar(
        select(ActivityField).where(
            ActivityField.activity_id == activity_id,
            ActivityField.field_key == payload.field_key,
        )
    )
    if existing is not None:
        raise ConfigurationConflictError("Activity field key already exists")
    field = ActivityField(activity_id=activity_id, **payload.model_dump())
    field.is_active = True
    field.is_archived = False
    session.add(field)
    await session.flush()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ACTIVITY_FIELD",
        entity_id=field.id,
        action="ACTIVITY_FIELD_CREATED",
        after_data={"activity_id": activity_id, **payload.model_dump()},
    )
    await session.commit()
    await session.refresh(field)
    return field


async def update_activity_field(
    session: AsyncSession,
    *,
    admin: User,
    field_id: uuid.UUID,
    payload: ActivityFieldUpdateRequest,
) -> ActivityField:
    field = await session.scalar(
        select(ActivityField)
        .join(Activity, Activity.id == ActivityField.activity_id)
        .where(
            ActivityField.id == field_id,
            Activity.organization_id == admin.organization_id,
        )
    )
    if field is None:
        raise ConfigurationNotFoundError("Activity field not found")
    if field.is_archived:
        raise ConfigurationConflictError("Archived field cannot be edited")
    before = {
        "label": field.label,
        "display_order": field.display_order,
    }
    for key in payload.model_fields_set:
        setattr(field, key, getattr(payload, key))
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ACTIVITY_FIELD",
        entity_id=field.id,
        action="ACTIVITY_FIELD_UPDATED",
        before_data=before,
        after_data={
            "label": field.label,
            "display_order": field.display_order,
        },
    )
    await session.commit()
    await session.refresh(field)
    return field


async def archive_activity_field(
    session: AsyncSession,
    *,
    admin: User,
    field_id: uuid.UUID,
    reason: str,
) -> ActivityField:
    field = await session.scalar(
        select(ActivityField)
        .join(Activity, Activity.id == ActivityField.activity_id)
        .where(ActivityField.id == field_id, Activity.organization_id == admin.organization_id)
    )
    if field is None:
        raise ConfigurationNotFoundError("Activity field not found")
    if not field.is_archived:
        field.is_active = False
        field.is_archived = True
        await add_audit_log(
            session,
            organization_id=admin.organization_id,
            actor_user_id=admin.id,
            entity_type="ACTIVITY_FIELD",
            entity_id=field.id,
            action="ACTIVITY_FIELD_ARCHIVED",
            reason=reason,
        )
        await session.commit()
        await session.refresh(field)
    return field


async def list_scoring_rules(
    session: AsyncSession,
    organization_id: uuid.UUID,
    activity_id: uuid.UUID | None = None,
) -> list[ScoringRule]:
    stmt = select(ScoringRule).where(ScoringRule.organization_id == organization_id)
    if activity_id is not None:
        stmt = stmt.where(ScoringRule.activity_id == activity_id)
    result = await session.execute(stmt.order_by(ScoringRule.name))
    return list(result.scalars())


async def create_scoring_rule(
    session: AsyncSession,
    *,
    admin: User,
    payload: ScoringRuleCreateRequest,
) -> ScoringRule:
    activity = await session.scalar(
        select(Activity).where(
            Activity.id == payload.activity_id,
            Activity.organization_id == admin.organization_id,
            Activity.is_archived.is_(False),
        )
    )
    if activity is None:
        raise ConfigurationNotFoundError("Activity not found")
    rule = ScoringRule(
        organization_id=admin.organization_id,
        activity_id=payload.activity_id,
        name=payload.name.strip(),
        rule_type=payload.rule_type,
        is_active=True,
        is_archived=False,
        created_by_id=admin.id,
    )
    session.add(rule)
    await session.flush()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="SCORING_RULE",
        entity_id=rule.id,
        action="SCORING_RULE_CREATED",
        after_data={"activity_id": payload.activity_id, "name": rule.name, "rule_type": rule.rule_type},
    )
    await session.commit()
    await session.refresh(rule)
    return rule


async def update_scoring_rule(
    session: AsyncSession,
    *, admin: User, rule_id: uuid.UUID, payload: ScoringRuleUpdateRequest
) -> ScoringRule:
    rule = await session.scalar(select(ScoringRule).where(ScoringRule.id == rule_id, ScoringRule.organization_id == admin.organization_id))
    if rule is None:
        raise ConfigurationNotFoundError("Scoring rule not found")
    if rule.is_archived:
        raise ConfigurationConflictError("Archived scoring rule cannot be edited")
    before = {"name": rule.name}
    rule.name = payload.name.strip()
    await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="SCORING_RULE", entity_id=rule.id, action="SCORING_RULE_UPDATED", before_data=before, after_data={"name": rule.name})
    await session.commit(); await session.refresh(rule)
    return rule


async def archive_scoring_rule(session: AsyncSession, *, admin: User, rule_id: uuid.UUID, reason: str) -> ScoringRule:
    rule = await session.scalar(select(ScoringRule).where(ScoringRule.id == rule_id, ScoringRule.organization_id == admin.organization_id))
    if rule is None:
        raise ConfigurationNotFoundError("Scoring rule not found")
    if not rule.is_archived:
        rule.is_active = False; rule.is_archived = True
        await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="SCORING_RULE", entity_id=rule.id, action="SCORING_RULE_ARCHIVED", reason=reason)
        await session.commit(); await session.refresh(rule)
    return rule


async def list_scoring_rule_versions(session: AsyncSession, *, organization_id: uuid.UUID, rule_id: uuid.UUID) -> list[ScoringRuleVersion]:
    rule = await session.scalar(select(ScoringRule).where(ScoringRule.id == rule_id, ScoringRule.organization_id == organization_id))
    if rule is None:
        raise ConfigurationNotFoundError("Scoring rule not found")
    result = await session.execute(select(ScoringRuleVersion).where(ScoringRuleVersion.scoring_rule_id == rule_id).order_by(ScoringRuleVersion.version_number))
    return list(result.scalars())


async def create_scoring_rule_version(session: AsyncSession, *, admin: User, rule_id: uuid.UUID, payload: ScoringRuleVersionCreateRequest) -> ScoringRuleVersion:
    rule = await session.scalar(select(ScoringRule).where(ScoringRule.id == rule_id, ScoringRule.organization_id == admin.organization_id, ScoringRule.is_archived.is_(False)))
    if rule is None:
        raise ConfigurationNotFoundError("Scoring rule not found")
    org = await _get_org(session, admin.organization_id)
    target = _validate_pending_week(org, payload.effective_from_week)
    pending = await session.scalar(select(ScoringRuleVersion).where(ScoringRuleVersion.scoring_rule_id == rule_id, ScoringRuleVersion.status == VersionStatus.PENDING))
    if pending is not None:
        raise ConfigurationConflictError("A pending version already exists; edit that pending version instead")
    _validate_executable_rule_version(
        rule, max_score=payload.max_score, configuration=payload.configuration
    )
    max_version = await session.scalar(select(func.max(ScoringRuleVersion.version_number)).where(ScoringRuleVersion.scoring_rule_id == rule_id)) or 0
    version = ScoringRuleVersion(scoring_rule_id=rule_id, version_number=max_version + 1, effective_from_week=target, status=VersionStatus.PENDING, max_score=payload.max_score, rounding_mode=payload.rounding_mode, configuration=payload.configuration, created_by_id=admin.id)
    session.add(version); await session.flush()
    await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="SCORING_RULE_VERSION", entity_id=version.id, action="SCORING_RULE_VERSION_PENDING_CREATED", after_data={"scoring_rule_id": rule_id, "version_number": version.version_number, "effective_from_week": target, "max_score": version.max_score})
    await session.commit(); await session.refresh(version)
    return version


async def update_scoring_rule_version(session: AsyncSession, *, admin: User, version_id: uuid.UUID, payload: ScoringRuleVersionUpdateRequest) -> ScoringRuleVersion:
    version = await session.scalar(
        select(ScoringRuleVersion)
        .join(ScoringRule, ScoringRule.id == ScoringRuleVersion.scoring_rule_id)
        .options(selectinload(ScoringRuleVersion.scoring_rule))
        .where(
            ScoringRuleVersion.id == version_id,
            ScoringRule.organization_id == admin.organization_id,
        )
    )
    if version is None:
        raise ConfigurationNotFoundError("Scoring rule version not found")
    if version.status != VersionStatus.PENDING:
        raise ImmutableVersionError("Only PENDING scoring rule versions may be edited")
    org = await _get_org(session, admin.organization_id)
    before = {"effective_from_week": version.effective_from_week, "max_score": version.max_score, "rounding_mode": version.rounding_mode, "configuration": version.configuration}
    prospective_max_score = (
        payload.max_score if "max_score" in payload.model_fields_set else version.max_score
    )
    prospective_configuration = (
        payload.configuration
        if "configuration" in payload.model_fields_set
        else version.configuration
    )
    _validate_executable_rule_version(
        version.scoring_rule,
        max_score=prospective_max_score,
        configuration=prospective_configuration,
    )
    if "effective_from_week" in payload.model_fields_set:
        version.effective_from_week = _validate_pending_week(org, payload.effective_from_week)
    for key in ("max_score", "rounding_mode", "configuration"):
        if key in payload.model_fields_set:
            setattr(version, key, getattr(payload, key))
    await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="SCORING_RULE_VERSION", entity_id=version.id, action="SCORING_RULE_VERSION_PENDING_UPDATED", before_data=before, after_data={"effective_from_week": version.effective_from_week, "max_score": version.max_score, "rounding_mode": version.rounding_mode, "configuration": version.configuration})
    await session.commit(); await session.refresh(version)
    return version


async def list_standards(session: AsyncSession, organization_id: uuid.UUID, activity_id: uuid.UUID | None = None) -> list[Standard]:
    stmt = select(Standard).where(Standard.organization_id == organization_id)
    if activity_id is not None:
        stmt = stmt.where(Standard.activity_id == activity_id)
    result = await session.execute(stmt.order_by(Standard.name)); return list(result.scalars())


async def create_standard(session: AsyncSession, *, admin: User, payload: StandardCreateRequest) -> Standard:
    activity = await session.scalar(select(Activity).where(Activity.id == payload.activity_id, Activity.organization_id == admin.organization_id, Activity.is_archived.is_(False)))
    if activity is None: raise ConfigurationNotFoundError("Activity not found")
    standard = Standard(organization_id=admin.organization_id, activity_id=payload.activity_id, name=payload.name.strip(), is_active=True, is_archived=False, created_by_id=admin.id)
    session.add(standard); await session.flush()
    await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="STANDARD", entity_id=standard.id, action="STANDARD_CREATED", after_data={"activity_id": payload.activity_id, "name": standard.name})
    await session.commit(); await session.refresh(standard); return standard


async def update_standard(session: AsyncSession, *, admin: User, standard_id: uuid.UUID, payload: StandardUpdateRequest) -> Standard:
    standard = await session.scalar(select(Standard).where(Standard.id == standard_id, Standard.organization_id == admin.organization_id))
    if standard is None: raise ConfigurationNotFoundError("Standard not found")
    if standard.is_archived: raise ConfigurationConflictError("Archived standard cannot be edited")
    before={"name":standard.name}; standard.name=payload.name.strip()
    await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="STANDARD", entity_id=standard.id, action="STANDARD_UPDATED", before_data=before, after_data={"name":standard.name})
    await session.commit(); await session.refresh(standard); return standard


async def archive_standard(session: AsyncSession, *, admin: User, standard_id: uuid.UUID, reason: str) -> Standard:
    standard=await session.scalar(select(Standard).where(Standard.id==standard_id, Standard.organization_id==admin.organization_id))
    if standard is None: raise ConfigurationNotFoundError("Standard not found")
    if not standard.is_archived:
        standard.is_active=False; standard.is_archived=True
        await add_audit_log(session, organization_id=admin.organization_id, actor_user_id=admin.id, entity_type="STANDARD", entity_id=standard.id, action="STANDARD_ARCHIVED", reason=reason)
        await session.commit(); await session.refresh(standard)
    return standard


async def list_standard_versions(session: AsyncSession, *, organization_id: uuid.UUID, standard_id: uuid.UUID) -> list[StandardVersion]:
    standard=await session.scalar(select(Standard).where(Standard.id==standard_id, Standard.organization_id==organization_id))
    if standard is None: raise ConfigurationNotFoundError("Standard not found")
    result=await session.execute(select(StandardVersion).where(StandardVersion.standard_id==standard_id).order_by(StandardVersion.version_number)); return list(result.scalars())


async def create_standard_version(
    session: AsyncSession,
    *,
    admin: User,
    standard_id: uuid.UUID,
    payload: StandardVersionCreateRequest,
) -> StandardVersion:
    standard = await session.scalar(
        select(Standard).where(
            Standard.id == standard_id,
            Standard.organization_id == admin.organization_id,
            Standard.is_archived.is_(False),
        )
    )
    if standard is None:
        raise ConfigurationNotFoundError("Standard not found")
    org = await _get_org(session, admin.organization_id)
    target = _validate_pending_week(org, payload.effective_from_week)
    pending = await session.scalar(
        select(StandardVersion).where(
            StandardVersion.standard_id == standard_id,
            StandardVersion.status == VersionStatus.PENDING,
        )
    )
    if pending is not None:
        raise ConfigurationConflictError(
            "A pending version already exists; edit that pending version instead"
        )
    await _validate_standard_version_definition(
        session,
        standard=standard,
        period=payload.period,
        target_definition=payload.target_definition,
    )
    max_version = await session.scalar(
        select(func.max(StandardVersion.version_number)).where(
            StandardVersion.standard_id == standard_id
        )
    ) or 0
    version = StandardVersion(
        standard_id=standard_id,
        version_number=max_version + 1,
        effective_from_week=target,
        period=payload.period,
        target_definition=payload.target_definition,
        status=VersionStatus.PENDING,
        created_by_id=admin.id,
    )
    session.add(version)
    await session.flush()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="STANDARD_VERSION",
        entity_id=version.id,
        action="STANDARD_VERSION_PENDING_CREATED",
        after_data={
            "standard_id": standard_id,
            "version_number": version.version_number,
            "effective_from_week": target,
            "period": version.period,
            "target_definition": version.target_definition,
        },
    )
    await session.commit()
    await session.refresh(version)
    return version


async def update_standard_version(
    session: AsyncSession,
    *,
    admin: User,
    version_id: uuid.UUID,
    payload: StandardVersionUpdateRequest,
) -> StandardVersion:
    version = await session.scalar(
        select(StandardVersion)
        .join(Standard, Standard.id == StandardVersion.standard_id)
        .where(
            StandardVersion.id == version_id,
            Standard.organization_id == admin.organization_id,
        )
    )
    if version is None:
        raise ConfigurationNotFoundError("Standard version not found")
    if version.status != VersionStatus.PENDING:
        raise ImmutableVersionError("Only PENDING standard versions may be edited")
    standard = await session.get(Standard, version.standard_id)
    if standard is None:
        raise ConfigurationNotFoundError("Standard not found")
    org = await _get_org(session, admin.organization_id)
    proposed_week = version.effective_from_week
    proposed_period = version.period
    proposed_definition = version.target_definition
    if "effective_from_week" in payload.model_fields_set:
        proposed_week = _validate_pending_week(org, payload.effective_from_week)
    if "period" in payload.model_fields_set:
        proposed_period = payload.period
    if "target_definition" in payload.model_fields_set:
        proposed_definition = payload.target_definition
    await _validate_standard_version_definition(
        session,
        standard=standard,
        period=proposed_period,
        target_definition=proposed_definition,
    )
    before = {
        "effective_from_week": version.effective_from_week,
        "period": version.period,
        "target_definition": version.target_definition,
    }
    version.effective_from_week = proposed_week
    version.period = proposed_period
    version.target_definition = proposed_definition
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="STANDARD_VERSION",
        entity_id=version.id,
        action="STANDARD_VERSION_PENDING_UPDATED",
        before_data=before,
        after_data={
            "effective_from_week": version.effective_from_week,
            "period": version.period,
            "target_definition": version.target_definition,
        },
    )
    await session.commit()
    await session.refresh(version)
    return version


async def list_category_configs(session: AsyncSession, *, organization_id: uuid.UUID, category_id: uuid.UUID | None = None, activity_id: uuid.UUID | None = None) -> list[CategoryActivityConfig]:
    stmt=select(CategoryActivityConfig).where(CategoryActivityConfig.organization_id==organization_id)
    if category_id is not None: stmt=stmt.where(CategoryActivityConfig.category_id==category_id)
    if activity_id is not None: stmt=stmt.where(CategoryActivityConfig.activity_id==activity_id)
    result=await session.execute(stmt.order_by(CategoryActivityConfig.category_id,CategoryActivityConfig.activity_id,CategoryActivityConfig.version_number)); return list(result.scalars())


async def _validate_category_config_ownership(session: AsyncSession, admin: User, config: CategoryActivityConfig) -> None:
    category=await session.scalar(select(DevoteeCategory).where(DevoteeCategory.id==config.category_id,DevoteeCategory.organization_id==admin.organization_id,DevoteeCategory.is_archived.is_(False)))
    if category is None: raise ConfigurationNotFoundError("Devotee category not found")
    activity=await session.scalar(select(Activity).where(Activity.id==config.activity_id,Activity.organization_id==admin.organization_id,Activity.is_archived.is_(False)))
    if activity is None: raise ConfigurationNotFoundError("Activity not found")
    rule=None
    if config.scoring_rule_id is not None:
        rule=await session.scalar(select(ScoringRule).where(ScoringRule.id==config.scoring_rule_id,ScoringRule.organization_id==admin.organization_id,ScoringRule.is_archived.is_(False)))
    standard=None
    if config.standard_id is not None:
        standard=await session.scalar(select(Standard).where(Standard.id==config.standard_id,Standard.organization_id==admin.organization_id,Standard.is_archived.is_(False)))
    try:
        validate_category_activity_config(config, scoring_rule=rule, standard=standard)
    except ConfigurationValidationError as exc:
        raise ConfigurationConflictError(str(exc)) from exc


async def create_category_config(session: AsyncSession, *, admin: User, payload: CategoryActivityConfigCreateRequest) -> CategoryActivityConfig:
    org=await _get_org(session,admin.organization_id); target=_validate_pending_week(org,payload.effective_from_week)
    pending=await session.scalar(select(CategoryActivityConfig).where(CategoryActivityConfig.organization_id==admin.organization_id,CategoryActivityConfig.category_id==payload.category_id,CategoryActivityConfig.activity_id==payload.activity_id,CategoryActivityConfig.status==VersionStatus.PENDING))
    if pending is not None: raise ConfigurationConflictError("A pending category/activity config already exists; edit it instead")
    max_version=await session.scalar(select(func.max(CategoryActivityConfig.version_number)).where(CategoryActivityConfig.category_id==payload.category_id,CategoryActivityConfig.activity_id==payload.activity_id)) or 0
    config=CategoryActivityConfig(organization_id=admin.organization_id,category_id=payload.category_id,activity_id=payload.activity_id,version_number=max_version+1,effective_from_week=target,is_applicable=payload.is_applicable,scoring_type=payload.scoring_type,weekly_aggregation=payload.weekly_aggregation,scoring_rule_id=payload.scoring_rule_id,standard_id=payload.standard_id,counts_toward_card_fill=payload.counts_toward_card_fill,status=VersionStatus.PENDING,created_by_id=admin.id)
    await _validate_category_config_ownership(session,admin,config)
    session.add(config); await session.flush()
    await add_audit_log(session,organization_id=admin.organization_id,actor_user_id=admin.id,entity_type="CATEGORY_ACTIVITY_CONFIG",entity_id=config.id,action="CATEGORY_ACTIVITY_CONFIG_PENDING_CREATED",after_data={"category_id":config.category_id,"activity_id":config.activity_id,"version_number":config.version_number,"effective_from_week":target,"scoring_type":config.scoring_type})
    await session.commit(); await session.refresh(config); return config


async def update_category_config(session: AsyncSession, *, admin: User, config_id: uuid.UUID, payload: CategoryActivityConfigUpdateRequest) -> CategoryActivityConfig:
    config=await session.scalar(select(CategoryActivityConfig).where(CategoryActivityConfig.id==config_id,CategoryActivityConfig.organization_id==admin.organization_id))
    if config is None: raise ConfigurationNotFoundError("Category activity config not found")
    if config.status!=VersionStatus.PENDING: raise ImmutableVersionError("Only PENDING category activity configs may be edited")
    org=await _get_org(session,admin.organization_id)
    before={"effective_from_week":config.effective_from_week,"is_applicable":config.is_applicable,"scoring_type":config.scoring_type,"weekly_aggregation":config.weekly_aggregation,"scoring_rule_id":config.scoring_rule_id,"standard_id":config.standard_id,"counts_toward_card_fill":config.counts_toward_card_fill}
    if "effective_from_week" in payload.model_fields_set: config.effective_from_week=_validate_pending_week(org,payload.effective_from_week)
    for key in ("is_applicable","scoring_type","weekly_aggregation","scoring_rule_id","standard_id","counts_toward_card_fill"):
        if key in payload.model_fields_set: setattr(config,key,getattr(payload,key))
    await _validate_category_config_ownership(session,admin,config)
    await add_audit_log(session,organization_id=admin.organization_id,actor_user_id=admin.id,entity_type="CATEGORY_ACTIVITY_CONFIG",entity_id=config.id,action="CATEGORY_ACTIVITY_CONFIG_PENDING_UPDATED",before_data=before,after_data={"effective_from_week":config.effective_from_week,"is_applicable":config.is_applicable,"scoring_type":config.scoring_type,"weekly_aggregation":config.weekly_aggregation,"scoring_rule_id":config.scoring_rule_id,"standard_id":config.standard_id,"counts_toward_card_fill":config.counts_toward_card_fill})
    await session.commit(); await session.refresh(config); return config


def _organization_settings_snapshot(row: Organization | OrganizationSettingVersion) -> dict[str, Any]:
    return {
        "timezone": row.timezone,
        "week_start_day": row.week_start_day,
        "daily_finalize_time": row.daily_finalize_time,
        "promotion_month": row.promotion_month,
    }


async def get_current_organization_setting_version(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> OrganizationSettingVersion:
    org = await _get_org(session, organization_id)
    version = await session.scalar(
        select(OrganizationSettingVersion).where(
            OrganizationSettingVersion.organization_id == organization_id,
            OrganizationSettingVersion.status == VersionStatus.ACTIVE,
        )
    )
    if version is None:
        raise ConfigurationNotFoundError(
            "Active organization settings version not found; run migrations/seed first"
        )
    if _organization_settings_snapshot(version) != _organization_settings_snapshot(org):
        raise ConfigurationConflictError(
            "Active organization settings history does not match the organizations row"
        )
    return version


async def list_organization_setting_versions(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
) -> list[OrganizationSettingVersion]:
    result = await session.execute(
        select(OrganizationSettingVersion)
        .where(OrganizationSettingVersion.organization_id == organization_id)
        .order_by(OrganizationSettingVersion.version_number)
    )
    return list(result.scalars())


async def create_organization_setting_version(
    session: AsyncSession,
    *,
    admin: User,
    payload: OrganizationSettingVersionCreateRequest,
) -> OrganizationSettingVersion:
    org = await _get_org(session, admin.organization_id)
    target = _validate_pending_week(org, payload.effective_from_week)

    pending = await session.scalar(
        select(OrganizationSettingVersion).where(
            OrganizationSettingVersion.organization_id == admin.organization_id,
            OrganizationSettingVersion.status == VersionStatus.PENDING,
        )
    )
    if pending is not None:
        raise ConfigurationConflictError(
            "A pending organization settings version already exists; edit it instead"
        )

    values = _organization_settings_snapshot(org)
    for key in (
        "timezone",
        "week_start_day",
        "daily_finalize_time",
        "promotion_month",
    ):
        if key in payload.model_fields_set:
            values[key] = getattr(payload, key)

    if values == _organization_settings_snapshot(org):
        raise ConfigurationConflictError(
            "Pending organization settings must change at least one active setting"
        )

    max_version = await session.scalar(
        select(func.max(OrganizationSettingVersion.version_number)).where(
            OrganizationSettingVersion.organization_id == admin.organization_id
        )
    ) or 0

    version = OrganizationSettingVersion(
        organization_id=admin.organization_id,
        version_number=max_version + 1,
        effective_from_week=target,
        status=VersionStatus.PENDING,
        created_by_id=admin.id,
        **values,
    )
    session.add(version)
    await session.flush()
    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ORGANIZATION_SETTING_VERSION",
        entity_id=version.id,
        action="ORGANIZATION_SETTING_VERSION_PENDING_CREATED",
        before_data=_organization_settings_snapshot(org),
        after_data={
            **_organization_settings_snapshot(version),
            "version_number": version.version_number,
            "effective_from_week": version.effective_from_week,
        },
    )
    await session.commit()
    await session.refresh(version)
    return version


async def update_organization_setting_version(
    session: AsyncSession,
    *,
    admin: User,
    version_id: uuid.UUID,
    payload: OrganizationSettingVersionUpdateRequest,
) -> OrganizationSettingVersion:
    version = await session.scalar(
        select(OrganizationSettingVersion).where(
            OrganizationSettingVersion.id == version_id,
            OrganizationSettingVersion.organization_id == admin.organization_id,
        )
    )
    if version is None:
        raise ConfigurationNotFoundError("Organization settings version not found")
    if version.status != VersionStatus.PENDING:
        raise ImmutableVersionError(
            "Only PENDING organization settings versions may be edited"
        )

    org = await _get_org(session, admin.organization_id)
    before = {
        **_organization_settings_snapshot(version),
        "effective_from_week": version.effective_from_week,
    }
    if "effective_from_week" in payload.model_fields_set:
        version.effective_from_week = _validate_pending_week(
            org, payload.effective_from_week
        )
    for key in (
        "timezone",
        "week_start_day",
        "daily_finalize_time",
        "promotion_month",
    ):
        if key in payload.model_fields_set:
            setattr(version, key, getattr(payload, key))

    if _organization_settings_snapshot(version) == _organization_settings_snapshot(org):
        raise ConfigurationConflictError(
            "Pending organization settings must differ from the active settings"
        )

    await add_audit_log(
        session,
        organization_id=admin.organization_id,
        actor_user_id=admin.id,
        entity_type="ORGANIZATION_SETTING_VERSION",
        entity_id=version.id,
        action="ORGANIZATION_SETTING_VERSION_PENDING_UPDATED",
        before_data=before,
        after_data={
            **_organization_settings_snapshot(version),
            "effective_from_week": version.effective_from_week,
        },
    )
    await session.commit()
    await session.refresh(version)
    return version


async def activate_due_configuration(
    session: AsyncSession,
    *,
    admin: User | None = None,
    organization_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Activate due versioned configuration for Admin or scheduler execution.

    Scheduler execution uses a NULL audit actor and may inject a deterministic ``now_utc``.
    The organization settings active at the start of the transaction define which week
    boundary is currently being crossed.
    """
    if admin is not None:
        org_id = admin.organization_id
        actor_id = admin.id
    else:
        if organization_id is None:
            raise ConfigurationAdminError("organization_id is required for system activation")
        org_id = organization_id
        actor_id = actor_user_id
    org = await _get_org(session, org_id)

    # Resolve "due" using the settings that are active at the start of this transaction.
    # If the same activation changes timezone/week-start, that new interpretation applies
    # only after this boundary has been crossed.
    today = organization_local_date(org.timezone, now_utc=now_utc)
    current_week_start, _ = get_week_bounds(today, org.week_start_day)

    scoring_versions = list(
        (
            await session.execute(
                select(ScoringRuleVersion)
                .join(ScoringRule, ScoringRule.id == ScoringRuleVersion.scoring_rule_id)
                .where(
                    ScoringRule.organization_id == org_id,
                    ScoringRuleVersion.status == VersionStatus.PENDING,
                    ScoringRuleVersion.effective_from_week <= current_week_start,
                )
            )
        ).scalars()
    )
    standard_versions = list(
        (
            await session.execute(
                select(StandardVersion)
                .join(Standard, Standard.id == StandardVersion.standard_id)
                .where(
                    Standard.organization_id == org_id,
                    StandardVersion.status == VersionStatus.PENDING,
                    StandardVersion.effective_from_week <= current_week_start,
                )
            )
        ).scalars()
    )
    category_configs = list(
        (
            await session.execute(
                select(CategoryActivityConfig).where(
                    CategoryActivityConfig.organization_id == org_id,
                    CategoryActivityConfig.status == VersionStatus.PENDING,
                    CategoryActivityConfig.effective_from_week <= current_week_start,
                )
            )
        ).scalars()
    )
    organization_setting_versions = list(
        (
            await session.execute(
                select(OrganizationSettingVersion).where(
                    OrganizationSettingVersion.organization_id == org_id,
                    OrganizationSettingVersion.status == VersionStatus.PENDING,
                    OrganizationSettingVersion.effective_from_week <= current_week_start,
                )
            )
        ).scalars()
    )

    # Preflight the entire due batch before mutating any status.  This keeps activation
    # transactional and prevents a malformed/under-specified config from becoming ACTIVE
    # only to fail later when a devotee card or weekly evaluation tries to execute it.
    for version in scoring_versions:
        rule = await session.get(ScoringRule, version.scoring_rule_id)
        if rule is None or rule.organization_id != org_id or rule.is_archived:
            raise ConfigurationConflictError(
                "Due scoring-rule version belongs to a missing/archived rule"
            )
        _validate_executable_rule_version(
            rule, max_score=version.max_score, configuration=version.configuration
        )

    for version in standard_versions:
        standard = await session.get(Standard, version.standard_id)
        if standard is None or standard.organization_id != org_id or standard.is_archived:
            raise ConfigurationConflictError(
                "Due standard version belongs to a missing/archived standard"
            )
        await _validate_standard_version_definition(
            session,
            standard=standard,
            period=version.period,
            target_definition=version.target_definition,
        )

    for config in category_configs:
        await _preflight_category_config_activation(session, config=config)

    for version in scoring_versions:
        active_versions = list(
            (
                await session.execute(
                    select(ScoringRuleVersion).where(
                        ScoringRuleVersion.scoring_rule_id == version.scoring_rule_id,
                        ScoringRuleVersion.status == VersionStatus.ACTIVE,
                        ScoringRuleVersion.id != version.id,
                    )
                )
            ).scalars()
        )
        for old in active_versions:
            old.status = VersionStatus.ARCHIVED
        version.status = VersionStatus.ACTIVE
        await add_audit_log(
            session,
            organization_id=org_id,
            actor_user_id=actor_id,
            entity_type="SCORING_RULE_VERSION",
            entity_id=version.id,
            action="SCORING_RULE_VERSION_ACTIVATED",
            after_data={
                "effective_from_week": version.effective_from_week,
                "version_number": version.version_number,
            },
        )

    for version in standard_versions:
        active_versions = list(
            (
                await session.execute(
                    select(StandardVersion).where(
                        StandardVersion.standard_id == version.standard_id,
                        StandardVersion.status == VersionStatus.ACTIVE,
                        StandardVersion.id != version.id,
                    )
                )
            ).scalars()
        )
        for old in active_versions:
            old.status = VersionStatus.ARCHIVED
        version.status = VersionStatus.ACTIVE
        await add_audit_log(
            session,
            organization_id=org_id,
            actor_user_id=actor_id,
            entity_type="STANDARD_VERSION",
            entity_id=version.id,
            action="STANDARD_VERSION_ACTIVATED",
            after_data={
                "effective_from_week": version.effective_from_week,
                "version_number": version.version_number,
            },
        )

    for config in category_configs:
        active_configs = list(
            (
                await session.execute(
                    select(CategoryActivityConfig).where(
                        CategoryActivityConfig.category_id == config.category_id,
                        CategoryActivityConfig.activity_id == config.activity_id,
                        CategoryActivityConfig.status == VersionStatus.ACTIVE,
                        CategoryActivityConfig.id != config.id,
                    )
                )
            ).scalars()
        )
        for old in active_configs:
            old.status = VersionStatus.ARCHIVED
        config.status = VersionStatus.ACTIVE
        await add_audit_log(
            session,
            organization_id=org_id,
            actor_user_id=actor_id,
            entity_type="CATEGORY_ACTIVITY_CONFIG",
            entity_id=config.id,
            action="CATEGORY_ACTIVITY_CONFIG_ACTIVATED",
            after_data={
                "effective_from_week": config.effective_from_week,
                "version_number": config.version_number,
            },
        )

    # There is intentionally at most one PENDING organization-settings row.  Keep the
    # loop for defensive handling of pre-existing inconsistent data, while the unique
    # effective-week constraint and service-layer rule prevent creating multiples.
    for version in organization_setting_versions:
        active_versions = list(
            (
                await session.execute(
                    select(OrganizationSettingVersion).where(
                        OrganizationSettingVersion.organization_id == org_id,
                        OrganizationSettingVersion.status == VersionStatus.ACTIVE,
                        OrganizationSettingVersion.id != version.id,
                    )
                )
            ).scalars()
        )
        before = _organization_settings_snapshot(org)
        for old in active_versions:
            old.status = VersionStatus.ARCHIVED
        version.status = VersionStatus.ACTIVE

        org.timezone = version.timezone
        org.week_start_day = version.week_start_day
        org.daily_finalize_time = version.daily_finalize_time
        org.promotion_month = version.promotion_month

        await add_audit_log(
            session,
            organization_id=org_id,
            actor_user_id=actor_id,
            entity_type="ORGANIZATION_SETTING_VERSION",
            entity_id=version.id,
            action="ORGANIZATION_SETTING_VERSION_ACTIVATED",
            before_data=before,
            after_data={
                **_organization_settings_snapshot(version),
                "effective_from_week": version.effective_from_week,
                "version_number": version.version_number,
            },
        )

    await session.commit()
    return {
        "effective_week": current_week_start,
        "scoring_rule_versions_activated": len(scoring_versions),
        "standard_versions_activated": len(standard_versions),
        "category_configs_activated": len(category_configs),
        "organization_setting_versions_activated": len(
            organization_setting_versions
        ),
    }
