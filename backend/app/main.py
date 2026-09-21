from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.services.scheduler import run_scheduler_tick, start_lifecycle_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = None
    if settings.scheduler_enabled:
        if settings.scheduler_run_on_startup:
            try:
                await run_scheduler_tick()
            except Exception:
                # Startup remains available for diagnostics; the recurring scheduler and
                # manual /admin/lifecycle/run-now endpoint can safely retry idempotently.
                logger.exception("Initial lifecycle scheduler tick failed")
        try:
            scheduler = start_lifecycle_scheduler()
        except Exception:
            logger.exception("Lifecycle scheduler could not start")
    app.state.lifecycle_scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
