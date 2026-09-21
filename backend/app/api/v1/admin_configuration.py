from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminDep, SessionDep
from app.schemas.configuration import (
    ActivationResult,
    ActivityCreateRequest,
    ActivityFieldCreateRequest,
    ActivityFieldPublic,
    ActivityFieldUpdateRequest,
    ActivityPublic,
    ActivityUpdateRequest,
    ArchiveRequest,
    CategoryActivityConfigCreateRequest,
    CategoryActivityConfigPublic,
    CategoryActivityConfigUpdateRequest,
    CategoryPublic,
    OrganizationSettingVersionCreateRequest,
    OrganizationSettingVersionPublic,
    OrganizationSettingVersionUpdateRequest,
    ScoringRuleCreateRequest,
    ScoringRulePublic,
    ScoringRuleUpdateRequest,
    ScoringRuleVersionCreateRequest,
    ScoringRuleVersionPublic,
    ScoringRuleVersionUpdateRequest,
    StandardCreateRequest,
    StandardPublic,
    StandardUpdateRequest,
    StandardVersionCreateRequest,
    StandardVersionPublic,
    StandardVersionUpdateRequest,
)
from app.services.configuration_admin import (
    ConfigurationAdminError,
    ConfigurationConflictError,
    ConfigurationNotFoundError,
    ImmutableVersionError,
    activate_due_configuration,
    archive_activity,
    archive_activity_field,
    archive_scoring_rule,
    archive_standard,
    create_activity,
    create_organization_setting_version,
    create_activity_field,
    create_category_config,
    create_scoring_rule,
    create_scoring_rule_version,
    create_standard,
    create_standard_version,
    list_activities,
    get_current_organization_setting_version,
    list_organization_setting_versions,
    list_categories,
    list_category_configs,
    list_scoring_rule_versions,
    list_scoring_rules,
    list_standard_versions,
    list_standards,
    update_activity,
    update_organization_setting_version,
    update_activity_field,
    update_category_config,
    update_scoring_rule,
    update_scoring_rule_version,
    update_standard,
    update_standard_version,
)

router = APIRouter(prefix="/admin/config", tags=["admin-configuration"])


def _raise_config_error(exc: Exception) -> None:
    if isinstance(exc, ConfigurationNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, (ConfigurationConflictError, ImmutableVersionError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, ConfigurationAdminError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/categories", response_model=list[CategoryPublic])
async def categories(admin: AdminDep, session: SessionDep) -> list[CategoryPublic]:
    rows = await list_categories(session, admin.organization_id)
    return [CategoryPublic.model_validate(row) for row in rows]


@router.get(
    "/organization-settings/current",
    response_model=OrganizationSettingVersionPublic,
)
async def current_organization_settings(
    admin: AdminDep,
    session: SessionDep,
) -> OrganizationSettingVersionPublic:
    try:
        row = await get_current_organization_setting_version(
            session, organization_id=admin.organization_id
        )
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return OrganizationSettingVersionPublic.model_validate(row)


@router.get(
    "/organization-settings/versions",
    response_model=list[OrganizationSettingVersionPublic],
)
async def organization_setting_versions(
    admin: AdminDep,
    session: SessionDep,
) -> list[OrganizationSettingVersionPublic]:
    rows = await list_organization_setting_versions(
        session, organization_id=admin.organization_id
    )
    return [OrganizationSettingVersionPublic.model_validate(row) for row in rows]


@router.post(
    "/organization-settings/versions",
    response_model=OrganizationSettingVersionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def add_organization_setting_version(
    payload: OrganizationSettingVersionCreateRequest,
    admin: AdminDep,
    session: SessionDep,
) -> OrganizationSettingVersionPublic:
    try:
        row = await create_organization_setting_version(
            session, admin=admin, payload=payload
        )
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return OrganizationSettingVersionPublic.model_validate(row)


@router.patch(
    "/organization-setting-versions/{version_id}",
    response_model=OrganizationSettingVersionPublic,
)
async def edit_organization_setting_version(
    version_id: uuid.UUID,
    payload: OrganizationSettingVersionUpdateRequest,
    admin: AdminDep,
    session: SessionDep,
) -> OrganizationSettingVersionPublic:
    try:
        row = await update_organization_setting_version(
            session, admin=admin, version_id=version_id, payload=payload
        )
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return OrganizationSettingVersionPublic.model_validate(row)


@router.get("/activities", response_model=list[ActivityPublic])
async def activities(
    admin: AdminDep,
    session: SessionDep,
    include_archived: bool = Query(default=False),
) -> list[ActivityPublic]:
    rows = await list_activities(session, admin.organization_id, include_archived=include_archived)
    return [ActivityPublic.model_validate(row) for row in rows]


@router.post("/activities", response_model=ActivityPublic, status_code=status.HTTP_201_CREATED)
async def add_activity(payload: ActivityCreateRequest, admin: AdminDep, session: SessionDep) -> ActivityPublic:
    try:
        row = await create_activity(session, admin=admin, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    # Newly created activities have no fields yet.
    return ActivityPublic.model_validate(row)


@router.patch("/activities/{activity_id}", response_model=ActivityPublic)
async def edit_activity(activity_id: uuid.UUID, payload: ActivityUpdateRequest, admin: AdminDep, session: SessionDep) -> ActivityPublic:
    try:
        row = await update_activity(session, admin=admin, activity_id=activity_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ActivityPublic.model_validate(row)


@router.post("/activities/{activity_id}/archive", response_model=ActivityPublic)
async def archive_activity_route(activity_id: uuid.UUID, payload: ArchiveRequest, admin: AdminDep, session: SessionDep) -> ActivityPublic:
    try:
        row = await archive_activity(session, admin=admin, activity_id=activity_id, reason=payload.reason)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ActivityPublic.model_validate(row)


@router.post("/activities/{activity_id}/fields", response_model=ActivityFieldPublic, status_code=status.HTTP_201_CREATED)
async def add_activity_field(activity_id: uuid.UUID, payload: ActivityFieldCreateRequest, admin: AdminDep, session: SessionDep) -> ActivityFieldPublic:
    try:
        row = await create_activity_field(session, admin=admin, activity_id=activity_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ActivityFieldPublic.model_validate(row)


@router.patch("/activity-fields/{field_id}", response_model=ActivityFieldPublic)
async def edit_activity_field(field_id: uuid.UUID, payload: ActivityFieldUpdateRequest, admin: AdminDep, session: SessionDep) -> ActivityFieldPublic:
    try:
        row = await update_activity_field(session, admin=admin, field_id=field_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ActivityFieldPublic.model_validate(row)


@router.post("/activity-fields/{field_id}/archive", response_model=ActivityFieldPublic)
async def archive_field(field_id: uuid.UUID, payload: ArchiveRequest, admin: AdminDep, session: SessionDep) -> ActivityFieldPublic:
    try:
        row = await archive_activity_field(session, admin=admin, field_id=field_id, reason=payload.reason)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ActivityFieldPublic.model_validate(row)


@router.get("/scoring-rules", response_model=list[ScoringRulePublic])
async def scoring_rules(admin: AdminDep, session: SessionDep, activity_id: uuid.UUID | None = Query(default=None)) -> list[ScoringRulePublic]:
    rows = await list_scoring_rules(session, admin.organization_id, activity_id)
    return [ScoringRulePublic.model_validate(row) for row in rows]


@router.post("/scoring-rules", response_model=ScoringRulePublic, status_code=status.HTTP_201_CREATED)
async def add_scoring_rule(payload: ScoringRuleCreateRequest, admin: AdminDep, session: SessionDep) -> ScoringRulePublic:
    try:
        row = await create_scoring_rule(session, admin=admin, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ScoringRulePublic.model_validate(row)


@router.patch("/scoring-rules/{rule_id}", response_model=ScoringRulePublic)
async def edit_scoring_rule(rule_id: uuid.UUID, payload: ScoringRuleUpdateRequest, admin: AdminDep, session: SessionDep) -> ScoringRulePublic:
    try:
        row = await update_scoring_rule(session, admin=admin, rule_id=rule_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ScoringRulePublic.model_validate(row)


@router.post("/scoring-rules/{rule_id}/archive", response_model=ScoringRulePublic)
async def archive_rule(rule_id: uuid.UUID, payload: ArchiveRequest, admin: AdminDep, session: SessionDep) -> ScoringRulePublic:
    try:
        row = await archive_scoring_rule(session, admin=admin, rule_id=rule_id, reason=payload.reason)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ScoringRulePublic.model_validate(row)


@router.get("/scoring-rules/{rule_id}/versions", response_model=list[ScoringRuleVersionPublic])
async def scoring_rule_versions(rule_id: uuid.UUID, admin: AdminDep, session: SessionDep) -> list[ScoringRuleVersionPublic]:
    try:
        rows = await list_scoring_rule_versions(session, organization_id=admin.organization_id, rule_id=rule_id)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return [ScoringRuleVersionPublic.model_validate(row) for row in rows]


@router.post("/scoring-rules/{rule_id}/versions", response_model=ScoringRuleVersionPublic, status_code=status.HTTP_201_CREATED)
async def add_scoring_rule_version(rule_id: uuid.UUID, payload: ScoringRuleVersionCreateRequest, admin: AdminDep, session: SessionDep) -> ScoringRuleVersionPublic:
    try:
        row = await create_scoring_rule_version(session, admin=admin, rule_id=rule_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ScoringRuleVersionPublic.model_validate(row)


@router.patch("/scoring-rule-versions/{version_id}", response_model=ScoringRuleVersionPublic)
async def edit_scoring_rule_version(version_id: uuid.UUID, payload: ScoringRuleVersionUpdateRequest, admin: AdminDep, session: SessionDep) -> ScoringRuleVersionPublic:
    try:
        row = await update_scoring_rule_version(session, admin=admin, version_id=version_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return ScoringRuleVersionPublic.model_validate(row)


@router.get("/standards", response_model=list[StandardPublic])
async def standards(admin: AdminDep, session: SessionDep, activity_id: uuid.UUID | None = Query(default=None)) -> list[StandardPublic]:
    rows = await list_standards(session, admin.organization_id, activity_id)
    return [StandardPublic.model_validate(row) for row in rows]


@router.post("/standards", response_model=StandardPublic, status_code=status.HTTP_201_CREATED)
async def add_standard(payload: StandardCreateRequest, admin: AdminDep, session: SessionDep) -> StandardPublic:
    try:
        row = await create_standard(session, admin=admin, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return StandardPublic.model_validate(row)


@router.patch("/standards/{standard_id}", response_model=StandardPublic)
async def edit_standard(standard_id: uuid.UUID, payload: StandardUpdateRequest, admin: AdminDep, session: SessionDep) -> StandardPublic:
    try:
        row = await update_standard(session, admin=admin, standard_id=standard_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return StandardPublic.model_validate(row)


@router.post("/standards/{standard_id}/archive", response_model=StandardPublic)
async def archive_standard_route(standard_id: uuid.UUID, payload: ArchiveRequest, admin: AdminDep, session: SessionDep) -> StandardPublic:
    try:
        row = await archive_standard(session, admin=admin, standard_id=standard_id, reason=payload.reason)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return StandardPublic.model_validate(row)


@router.get("/standards/{standard_id}/versions", response_model=list[StandardVersionPublic])
async def standard_versions(standard_id: uuid.UUID, admin: AdminDep, session: SessionDep) -> list[StandardVersionPublic]:
    try:
        rows = await list_standard_versions(session, organization_id=admin.organization_id, standard_id=standard_id)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return [StandardVersionPublic.model_validate(row) for row in rows]


@router.post("/standards/{standard_id}/versions", response_model=StandardVersionPublic, status_code=status.HTTP_201_CREATED)
async def add_standard_version(standard_id: uuid.UUID, payload: StandardVersionCreateRequest, admin: AdminDep, session: SessionDep) -> StandardVersionPublic:
    try:
        row = await create_standard_version(session, admin=admin, standard_id=standard_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return StandardVersionPublic.model_validate(row)


@router.patch("/standard-versions/{version_id}", response_model=StandardVersionPublic)
async def edit_standard_version(version_id: uuid.UUID, payload: StandardVersionUpdateRequest, admin: AdminDep, session: SessionDep) -> StandardVersionPublic:
    try:
        row = await update_standard_version(session, admin=admin, version_id=version_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return StandardVersionPublic.model_validate(row)


@router.get("/category-activity-configs", response_model=list[CategoryActivityConfigPublic])
async def category_activity_configs(admin: AdminDep, session: SessionDep, category_id: uuid.UUID | None = Query(default=None), activity_id: uuid.UUID | None = Query(default=None)) -> list[CategoryActivityConfigPublic]:
    rows = await list_category_configs(session, organization_id=admin.organization_id, category_id=category_id, activity_id=activity_id)
    return [CategoryActivityConfigPublic.model_validate(row) for row in rows]


@router.post("/category-activity-configs", response_model=CategoryActivityConfigPublic, status_code=status.HTTP_201_CREATED)
async def add_category_activity_config(payload: CategoryActivityConfigCreateRequest, admin: AdminDep, session: SessionDep) -> CategoryActivityConfigPublic:
    try:
        row = await create_category_config(session, admin=admin, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return CategoryActivityConfigPublic.model_validate(row)


@router.patch("/category-activity-configs/{config_id}", response_model=CategoryActivityConfigPublic)
async def edit_category_activity_config(config_id: uuid.UUID, payload: CategoryActivityConfigUpdateRequest, admin: AdminDep, session: SessionDep) -> CategoryActivityConfigPublic:
    try:
        row = await update_category_config(session, admin=admin, config_id=config_id, payload=payload)
    except ConfigurationAdminError as exc:
        _raise_config_error(exc)
    return CategoryActivityConfigPublic.model_validate(row)


@router.post("/activate-due", response_model=ActivationResult)
async def activate_due(admin: AdminDep, session: SessionDep) -> ActivationResult:
    """Activate due pending versions at the organization week boundary.

    This endpoint is intentionally Admin-only in Step 7. The later scheduler phase will
    call the same service logic under a PostgreSQL-backed job lock.
    """
    result = await activate_due_configuration(session, admin=admin)
    return ActivationResult(**result)
