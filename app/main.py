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

# 🔥 Core Infrastructure
from app.core.config import settings
from app.core.logger import setup_logging
from app.core.monitoring import init_sentry
from app.core.supabase import init_clients
from app.core.setup_middlewares import apply_middlewares
from app.core.exceptions import register_exception_handlers

# 🔥 Events & Cron
from app.events.registry import register_all_event_handlers
from app.cron.scheduler import start_cron_jobs

# 🔥 Routers
from app.api.v1.routers.health import router as health_router
from app.api.v1.api import api_router

# ── Initialization ────────────────────────────────────────────────────────────
setup_logging()
init_sentry()
logger = logging.getLogger(__name__)

# ── Lifespan — Startup & Shutdown ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("🚀 Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    
    # Initialize DB Connections asynchronously
    await init_clients()
    
    # Register Event Bus Handlers
    register_all_event_handlers()
    logger.info("✅ Application Event Bus ready")
    
    # Start background cron jobs (e.g., Abandoned Cart Sweeper)
    start_cron_jobs()
    logger.info("✅ Cron Scheduler started")
    
    yield  # Application handles live traffic here
    
    logger.info("👋 Shutting down %s", settings.APP_NAME)

# ── FastAPI App Instance ──────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs"# if settings.APP_ENV == "development" else None,
    redoc_url="/redoc"# if settings.APP_ENV == "development" else None,
    openapi_url="/openapi.json"# if settings.APP_ENV == "development" else None,
    lifespan=lifespan,
)

# ── Global App Configuration ──────────────────────────────────────────────────
# 1. Mount Security, CORS, Rate Limiters, and PureWindow Logger
apply_middlewares(app)

# 2. Mount Enterprise Error Handlers (Catches Domain Exceptions globally)
register_exception_handlers(app)

# ── Router Registration ───────────────────────────────────────────────────────
# Load Balancer Health Check (Root level)
app.include_router(health_router)

# Main Application APIs (Versioned)
app.include_router(api_router, prefix="/api/v1")