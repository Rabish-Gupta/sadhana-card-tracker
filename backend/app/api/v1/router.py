from fastapi import APIRouter

from app.api.v1 import (
    admin_configuration,
    admin_corrections,
    admin_lifecycle,
    admin_users,
    auth,
    daily_cards,
    lifecycle,
    monthly_reports,
    weekly_evaluations,
)


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(admin_users.router)
api_router.include_router(admin_lifecycle.router)
api_router.include_router(admin_configuration.router)
api_router.include_router(admin_corrections.router)
api_router.include_router(daily_cards.router)
api_router.include_router(lifecycle.router)
api_router.include_router(weekly_evaluations.router)
api_router.include_router(monthly_reports.router)
