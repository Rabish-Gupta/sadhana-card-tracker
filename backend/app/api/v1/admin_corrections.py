from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminDep, SessionDep
from app.schemas.daily_card import DailyCardPublic
from app.schemas.historical_correction import (
    HistoricalCardCorrectionRequest,
    HistoricalCardCorrectionResult,
    HistoricalCategoryCorrectionRequest,
    HistoricalCategoryCorrectionResult,
    HistoricalCategoryHistoryPublic,
)
from app.services.historical_corrections import (
    HistoricalCorrectionConflictError,
    HistoricalCorrectionError,
    HistoricalCorrectionNotFoundError,
    HistoricalCorrectionValidationError,
    correct_finalized_card,
    correct_historical_category,
    get_category_history_for_admin,
    get_finalized_card_for_admin,
)


router = APIRouter(prefix="/admin/corrections", tags=["admin-corrections"])


def _raise_correction_error(exc: Exception) -> None:
    if isinstance(exc, HistoricalCorrectionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, HistoricalCorrectionValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if isinstance(exc, HistoricalCorrectionConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get(
    "/devotees/{user_id}/cards/{card_date}",
    response_model=DailyCardPublic,
)
async def admin_get_historical_card(
    user_id: uuid.UUID,
    card_date: date,
    admin: AdminDep,
    session: SessionDep,
) -> DailyCardPublic:
    try:
        return await get_finalized_card_for_admin(
            session,
            admin=admin,
            devotee_user_id=user_id,
            card_date=card_date,
        )
    except HistoricalCorrectionError as exc:
        _raise_correction_error(exc)
    raise AssertionError("unreachable")


@router.patch(
    "/devotees/{user_id}/cards/{card_date}",
    response_model=HistoricalCardCorrectionResult,
)
async def admin_correct_historical_card(
    user_id: uuid.UUID,
    card_date: date,
    payload: HistoricalCardCorrectionRequest,
    admin: AdminDep,
    session: SessionDep,
) -> HistoricalCardCorrectionResult:
    try:
        return await correct_finalized_card(
            session,
            admin=admin,
            devotee_user_id=user_id,
            card_date=card_date,
            payload=payload,
        )
    except HistoricalCorrectionError as exc:
        _raise_correction_error(exc)
    raise AssertionError("unreachable")


@router.get(
    "/devotees/{user_id}/category-history",
    response_model=HistoricalCategoryHistoryPublic,
)
async def admin_get_category_history(
    user_id: uuid.UUID,
    admin: AdminDep,
    session: SessionDep,
) -> HistoricalCategoryHistoryPublic:
    try:
        return await get_category_history_for_admin(
            session,
            admin=admin,
            devotee_user_id=user_id,
        )
    except HistoricalCorrectionError as exc:
        _raise_correction_error(exc)
    raise AssertionError("unreachable")


@router.patch(
    "/devotees/{user_id}/category",
    response_model=HistoricalCategoryCorrectionResult,
)
async def admin_correct_historical_category(
    user_id: uuid.UUID,
    payload: HistoricalCategoryCorrectionRequest,
    admin: AdminDep,
    session: SessionDep,
) -> HistoricalCategoryCorrectionResult:
    try:
        return await correct_historical_category(
            session,
            admin=admin,
            devotee_user_id=user_id,
            payload=payload,
        )
    except HistoricalCorrectionError as exc:
        _raise_correction_error(exc)
    raise AssertionError("unreachable")
