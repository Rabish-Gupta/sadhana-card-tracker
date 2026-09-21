from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminDep, SessionDep
from app.core.enums import AccountStatus
from app.schemas.admin import (
    AccountStatusChangeRequest,
    AdminCreateDevoteeRequest,
    RejectionRequest,
)
from app.schemas.user import UserPublic
from app.services.users import (
    CategoryValidationError,
    DuplicateEmailError,
    InvalidAccountTransitionError,
    UserManagementError,
    UserNotFoundError,
    activate_devotee,
    approve_registration,
    create_devotee_by_admin,
    deactivate_devotee,
    list_devotees,
    reject_registration,
)


router = APIRouter(prefix="/admin", tags=["admin-users"])


def _raise_user_management_error(exc: Exception) -> None:
    if isinstance(exc, UserNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, DuplicateEmailError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, (InvalidAccountTransitionError, CategoryValidationError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/registrations/pending", response_model=list[UserPublic])
async def pending_registrations(admin: AdminDep, session: SessionDep) -> list[UserPublic]:
    users = await list_devotees(
        session,
        organization_id=admin.organization_id,
        account_status=AccountStatus.PENDING,
    )
    return [UserPublic.model_validate(user) for user in users]


@router.post("/registrations/{user_id}/approve", response_model=UserPublic)
async def approve(
    user_id: uuid.UUID,
    admin: AdminDep,
    session: SessionDep,
) -> UserPublic:
    try:
        user = await approve_registration(session, admin=admin, user_id=user_id)
    except UserManagementError as exc:
        _raise_user_management_error(exc)
    return UserPublic.model_validate(user)


@router.post("/registrations/{user_id}/reject", response_model=UserPublic)
async def reject(
    user_id: uuid.UUID,
    payload: RejectionRequest,
    admin: AdminDep,
    session: SessionDep,
) -> UserPublic:
    try:
        user = await reject_registration(
            session,
            admin=admin,
            user_id=user_id,
            reason=payload.reason,
        )
    except UserManagementError as exc:
        _raise_user_management_error(exc)
    return UserPublic.model_validate(user)


@router.post("/devotees", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def admin_create_devotee(
    payload: AdminCreateDevoteeRequest,
    admin: AdminDep,
    session: SessionDep,
) -> UserPublic:
    try:
        user = await create_devotee_by_admin(session, admin=admin, payload=payload)
    except UserManagementError as exc:
        _raise_user_management_error(exc)
    return UserPublic.model_validate(user)


@router.get("/devotees", response_model=list[UserPublic])
async def devotees(
    admin: AdminDep,
    session: SessionDep,
    account_status: AccountStatus | None = Query(default=None),
) -> list[UserPublic]:
    users = await list_devotees(
        session,
        organization_id=admin.organization_id,
        account_status=account_status,
    )
    return [UserPublic.model_validate(user) for user in users]


@router.post("/devotees/{user_id}/deactivate", response_model=UserPublic)
async def deactivate(
    user_id: uuid.UUID,
    payload: AccountStatusChangeRequest,
    admin: AdminDep,
    session: SessionDep,
) -> UserPublic:
    try:
        user = await deactivate_devotee(
            session,
            admin=admin,
            user_id=user_id,
            reason=payload.reason,
        )
    except UserManagementError as exc:
        _raise_user_management_error(exc)
    return UserPublic.model_validate(user)


@router.post("/devotees/{user_id}/activate", response_model=UserPublic)
async def activate(
    user_id: uuid.UUID,
    payload: AccountStatusChangeRequest,
    admin: AdminDep,
    session: SessionDep,
) -> UserPublic:
    try:
        user = await activate_devotee(
            session,
            admin=admin,
            user_id=user_id,
            reason=payload.reason,
        )
    except UserManagementError as exc:
        _raise_user_management_error(exc)
    return UserPublic.model_validate(user)
