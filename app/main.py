""" 
Luviio — FastAPI Application Factory (Enterprise Grade)
======================================================
Path: app/main.py

To run:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from typing import AsyncGenerator

from fastapi import FastAPI

from app.api.middlewares.audit import AdminAuditMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import configure_logging
from app.core.maintenance import maintenance_middleware
from app.core.monitoring import init_sentry
from app.core.setup_middlewares import apply_middlewares
from app.cron.registry import CRON_JOBS
from app.cron.scheduler import start_cron_jobs, stop_cron_jobs
from app.domains.auth.http_client import close_auth_http_client, init_auth_http_client
from app.events.bus import get_event_bus
from app.events.registry import register_all_event_handlers
from app.infrastructure.health.router import router as health_router
from app.infrastructure.social_share.router import router as social_share_router

configure_logging()
init_sentry()
logger = logging.getLogger(__name__)

_OUTBOX_LOOP_INTERVAL_SECONDS = 15
_OUTBOX_LOOP_TIMEOUT_SECONDS = 20
_OUTBOX_BATCH_SIZE = 20


async def _durable_outbox_loop() -> None:
    """Continuously drain durable events independently of APScheduler ownership.

    Multiple workers may run this loop safely because event_outbox claims are
    atomic. This keeps payment/order notifications alive even when the
    container-level APScheduler owner changes or is unavailable.
    """
    while True:
        try:
            processed = await asyncio.wait_for(
                get_event_bus().dispatch_outbox(limit=_OUTBOX_BATCH_SIZE),
                timeout=_OUTBOX_LOOP_TIMEOUT_SECONDS,
            )
            if processed:
                logger.info("[EVENT OUTBOX] Background loop dispatched %d durable events", processed)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            logger.error(
                "[EVENT OUTBOX] Background loop timed out after %ss",
                _OUTBOX_LOOP_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.exception("[EVENT OUTBOX] Background loop failed")

        await asyncio.sleep(_OUTBOX_LOOP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Application startup | service=%s env=%s", settings.APP_NAME, settings.APP_ENV)

    # Required runtime dependency: fail fast rather than serving a partially
    # initialized worker.
    try:
        await init_auth_http_client()
        logger.info("Auth HTTP client ready | pooled=true keep_alive=true")
    except Exception:
        logger.critical("Auth HTTP client initialization failed", exc_info=True)
        raise

    # Event handlers are required for the application's durable event flow.
    try:
        register_all_event_handlers()
        logger.info("Event bus ready | durable_outbox=true")
    except Exception:
        logger.critical("Event handler registration failed", exc_info=True)
        raise

    if not settings.email_configured:
        logger.warning("EMAIL NOT CONFIGURED — transactional emails are disabled")
    if not settings.push_configured:
        logger.warning("PUSH NOT CONFIGURED — web push notifications are disabled")

    # The durable outbox has its own worker loop. Event claims are atomic,
    # so this remains safe across multiple Gunicorn workers and does not rely
    # on a single APScheduler owner.
    outbox_task = asyncio.create_task(_durable_outbox_loop(), name="luviio-event-outbox")

    scheduler_started = start_cron_jobs()
    if not scheduler_started:
        logger.info(
            "Background scheduler not owned by this worker | tasks=%s",
            len(CRON_JOBS),
        )
    else:
        logger.info(
            "Background scheduler ready | tasks=%s",
            len(CRON_JOBS),
        )

    try:
        yield
    finally:
        outbox_task.cancel()
        with suppress(asyncio.CancelledError):
            await outbox_task
        stop_cron_jobs()
        await close_auth_http_client()
        logger.info("Application shutdown | service=%s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Minimal public endpoint used to verify that the API process is reachable."""
    if settings.is_production:
        return {"status": "ok"}

    return {
        "service": settings.APP_NAME,
        "status": "ok",
        "health": "/health/live",
        "api": "/api/v1",
    }


# FastAPI/Starlette makes the last registered middleware the outermost layer.
# Keep maintenance last so it short-circuits requests before audit, rate
# limiting, CORS and other inner request processing.
apply_middlewares(app)
app.add_middleware(AdminAuditMiddleware)
app.middleware("http")(maintenance_middleware)

register_exception_handlers(app)
app.include_router(health_router)
app.include_router(social_share_router)
app.include_router(api_router, prefix="/api/v1")
