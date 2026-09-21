from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DevoteeDep, SessionDep
from app.schemas.lifecycle import BhimaStatusChangeRequest, LifecycleStatusPublic
from app.services.lifecycle import (
    LifecycleConflictError,
    LifecycleError,
    LifecycleNotFoundError,
    LifecycleValidationError,
    get_lifecycle_status,
    request_bhima_status,
)

router = APIRouter(prefix="/lifecycle", tags=["devotee-lifecycle"])


def _raise_lifecycle_error(exc: LifecycleError) -> None:
    if isinstance(exc, LifecycleNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, LifecycleConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, LifecycleValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/status", response_model=LifecycleStatusPublic)
async def lifecycle_status(devotee: DevoteeDep, session: SessionDep) -> LifecycleStatusPublic:
    try:
        return await get_lifecycle_status(session, user=devotee)
    except LifecycleError as exc:
        _raise_lifecycle_error(exc)
    raise AssertionError("unreachable")


@router.post("/bhima-status", response_model=LifecycleStatusPublic)
async def change_bhima_status(
    payload: BhimaStatusChangeRequest,
    devotee: DevoteeDep,
    session: SessionDep,
) -> LifecycleStatusPublic:
    try:
        return await request_bhima_status(
            session,
            devotee=devotee,
            employment_status=payload.employment_status,
            reason=payload.reason,
        )
    except LifecycleError as exc:
        _raise_lifecycle_error(exc)
    raise AssertionError("unreachable")
