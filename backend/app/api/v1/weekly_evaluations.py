from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DevoteeDep, SessionDep
from app.schemas.weekly_evaluation import WeeklyEvaluationPublic
from app.services.weekly_evaluations import (
    PartialLifecycleWeekError,
    WeeklyEvaluationConfigurationError,
    WeeklyEvaluationError,
    WeeklyEvaluationNotFoundError,
    WeeklyEvaluationNotReadyError,
    get_latest_weekly_evaluation_public,
    get_weekly_evaluation_public,
)


router = APIRouter(prefix="/weekly", tags=["weekly-evaluations"])


def _raise_weekly_error(exc: Exception) -> None:
    if isinstance(exc, WeeklyEvaluationNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, (PartialLifecycleWeekError, WeeklyEvaluationNotReadyError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, WeeklyEvaluationConfigurationError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/latest", response_model=WeeklyEvaluationPublic)
async def latest_weekly_evaluation(
    devotee: DevoteeDep,
    session: SessionDep,
) -> WeeklyEvaluationPublic:
    try:
        return await get_latest_weekly_evaluation_public(session, user=devotee)
    except WeeklyEvaluationError as exc:
        _raise_weekly_error(exc)
    raise AssertionError("unreachable")


@router.get("/{week_start_date}", response_model=WeeklyEvaluationPublic)
async def weekly_evaluation(
    week_start_date: date,
    devotee: DevoteeDep,
    session: SessionDep,
) -> WeeklyEvaluationPublic:
    try:
        return await get_weekly_evaluation_public(
            session,
            user=devotee,
            week_start=week_start_date,
        )
    except WeeklyEvaluationError as exc:
        _raise_weekly_error(exc)
    raise AssertionError("unreachable")
