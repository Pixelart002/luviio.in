"""
Luviio — FastAPI Application Factory (Enterprise Grade)
======================================================
Path: app/main.py

To run:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.core.config import settings
from app.core.logger import setup_logging
from app.core.monitoring import init_sentry
from app.core.setup_middlewares import apply_middlewares
from app.core.exceptions import register_exception_handlers
from app.core.maintenance import maintenance_middleware
from app.events.registry import register_all_event_handlers
from app.cron.scheduler import start_cron_jobs
from app.infrastructure.health.router import router as health_router
from app.api.v1.api import api_router

setup_logging()
init_sentry()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("🚀 Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)

    register_all_event_handlers()
    logger.info("✅ Application Event Bus ready")

    start_cron_jobs()
    logger.info("✅ Cron Scheduler started")

    yield

    logger.info("👋 Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

apply_middlewares(app)
app.middleware("http")(maintenance_middleware)
register_exception_handlers(app)

# Root-level load-balancer health check.
app.include_router(health_router)

# Versioned business API.
app.include_router(api_router, prefix="/api/v1")
