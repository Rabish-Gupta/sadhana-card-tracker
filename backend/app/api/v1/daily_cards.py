from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DevoteeDep, SessionDep
from app.schemas.daily_card import DailyCardPublic, DailyCardUpdateRequest
from app.services.daily_cards import (
    DailyCardConfigurationError,
    DailyCardError,
    DailyCardNotEditableError,
    DailyCardNotFoundError,
    DailyCardValidationError,
    get_card_public,
    update_card_public,
)


router = APIRouter(prefix="/cards", tags=["daily-cards"])


def _raise_daily_card_error(exc: Exception) -> None:
    if isinstance(exc, DailyCardNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, DailyCardNotEditableError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, DailyCardValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if isinstance(exc, DailyCardConfigurationError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/today", response_model=DailyCardPublic)
async def today_card(devotee: DevoteeDep, session: SessionDep) -> DailyCardPublic:
    try:
        return await get_card_public(session, user=devotee)
    except DailyCardError as exc:
        _raise_daily_card_error(exc)
    raise AssertionError("unreachable")


@router.patch("/today", response_model=DailyCardPublic)
async def update_today_card(
    payload: DailyCardUpdateRequest,
    devotee: DevoteeDep,
    session: SessionDep,
) -> DailyCardPublic:
    try:
        return await update_card_public(session, user=devotee, payload=payload)
    except DailyCardError as exc:
        _raise_daily_card_error(exc)
    raise AssertionError("unreachable")


@router.get("/{card_date}", response_model=DailyCardPublic)
async def dated_card(
    card_date: date,
    devotee: DevoteeDep,
    session: SessionDep,
) -> DailyCardPublic:
    try:
        return await get_card_public(session, user=devotee, target_date=card_date)
    except DailyCardError as exc:
        _raise_daily_card_error(exc)
    raise AssertionError("unreachable")
