"""
Luviio — FastAPI Application Factory
=====================================
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

# 🔥 FIX: Updated imports for Event Registry and Cron
from app.events.registry import register_all_event_handlers
from app.cron.scheduler import start_cron_jobs

# 🔥 Routers
from app.api.health import router as health_router
from app.api.v1.api import api_router

# ── Initialization ────────────────────────────────────────────────────────────
setup_logging()
init_sentry()
logger = logging.getLogger(__name__)

# ── Lifespan — Startup & Shutdown ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("🚀 Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    
    # 🔥 FIX: Added 'await' here because init_clients is now an async function!
    await init_clients()
    
    # 🔥 FIX: Calling the renamed event registry function
    register_all_event_handlers()
    logger.info("✅ Application ready")
    
    # 🔥 Start background cron jobs (e.g. cart unlocker)
    start_cron_jobs()
    
    yield  # Application runs here
    
    logger.info("👋 Shutting down %s", settings.APP_NAME)

# ── FastAPI App Instance ──────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV == "development" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    openapi_url="/openapi.json" if settings.APP_ENV == "development" else None,
    lifespan=lifespan,
)

# ── App Configuration ─────────────────────────────────────────────────────────
apply_middlewares(app)
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(api_router, prefix="/api/v1")