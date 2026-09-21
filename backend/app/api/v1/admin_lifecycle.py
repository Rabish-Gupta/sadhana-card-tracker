from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminDep, SessionDep
from app.schemas.lifecycle import SahadevaReviewItem, SahadevaReviewRequest, SahadevaReviewResult
from app.services.lifecycle import (
    LifecycleConflictError,
    LifecycleError,
    LifecycleNotFoundError,
    LifecycleValidationError,
    list_sahadeva_reviews,
    schedule_sahadeva_review,
)
from app.services.scheduler import run_organization_lifecycle

router = APIRouter(prefix="/admin/lifecycle", tags=["admin-lifecycle"])


def _raise_lifecycle_error(exc: LifecycleError) -> None:
    if isinstance(exc, LifecycleNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, LifecycleConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, LifecycleValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/sahadeva-reviews", response_model=list[SahadevaReviewItem])
async def sahadeva_reviews(
    admin: AdminDep,
    session: SessionDep,
    include_not_due: bool = Query(default=False),
) -> list[SahadevaReviewItem]:
    try:
        return await list_sahadeva_reviews(
            session,
            organization_id=admin.organization_id,
            include_not_due=include_not_due,
        )
    except LifecycleError as exc:
        _raise_lifecycle_error(exc)
    raise AssertionError("unreachable")


@router.post(
    "/devotees/{user_id}/sahadeva-review",
    response_model=SahadevaReviewResult,
)
async def sahadeva_review(
    user_id: uuid.UUID,
    payload: SahadevaReviewRequest,
    admin: AdminDep,
    session: SessionDep,
) -> SahadevaReviewResult:
    try:
        return await schedule_sahadeva_review(
            session,
            admin=admin,
            devotee_user_id=user_id,
            decision=payload.decision,
            reason=payload.reason,
        )
    except LifecycleError as exc:
        _raise_lifecycle_error(exc)
    raise AssertionError("unreachable")


@router.post("/run-now")
async def run_lifecycle_now(admin: AdminDep) -> dict:
    """Admin diagnostic/manual retry. Production automation uses APScheduler."""

    return await run_organization_lifecycle(admin.organization_id)
