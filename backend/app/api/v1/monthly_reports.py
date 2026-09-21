from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.api.deps import DevoteeDep, SessionDep
from app.schemas.monthly_report import FourWeekReportPublic
from app.services.monthly_reports import (
    MonthlyReportError,
    MonthlyReportNotFoundError,
    MonthlyReportNotReadyError,
    get_four_week_report_public,
    get_latest_four_week_report_public,
)


router = APIRouter(prefix="/monthly", tags=["monthly-reports"])


def _raise_monthly_error(exc: Exception) -> None:
    if isinstance(exc, MonthlyReportNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, MonthlyReportNotReadyError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/latest", response_model=FourWeekReportPublic)
async def latest_monthly_report(
    devotee: DevoteeDep,
    session: SessionDep,
) -> FourWeekReportPublic:
    try:
        return await get_latest_four_week_report_public(session, user=devotee)
    except MonthlyReportError as exc:
        _raise_monthly_error(exc)
    raise AssertionError("unreachable")


@router.get("/{period_start_date}", response_model=FourWeekReportPublic)
async def monthly_report(
    period_start_date: date,
    devotee: DevoteeDep,
    session: SessionDep,
) -> FourWeekReportPublic:
    try:
        return await get_four_week_report_public(
            session,
            user=devotee,
            period_start=period_start_date,
        )
    except MonthlyReportError as exc:
        _raise_monthly_error(exc)
    raise AssertionError("unreachable")
