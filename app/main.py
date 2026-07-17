"""
Luviio — FastAPI Application Factory (Enterprise Grade)
======================================================
Path: app/main.py
To run: uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
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
from app.events.registry import register_all_event_handlers
from app.cron.scheduler import start_cron_jobs

from app.api.v1.routers.health import router as health_router
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
    
    logger.info("👋 Shutting down %s gracefully", settings.APP_NAME)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
    lifespan=lifespan,
)

# 1. Mount Security, CORS, Rate Limiters, and PureWindow Logger
apply_middlewares(app)

# 2. Mount Enterprise Error Handlers (Catches Domain Exceptions globally)
register_exception_handlers(app)

# 3. Router Registration
app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")