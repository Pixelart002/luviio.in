"""
Health Check Router — Async Enterprise Grade
============================================
Path: app/infrastructure/health/router.py

Infrastructure health endpoint used by load balancers and monitoring.
"""
import asyncio
import logging
import time
from fastapi import APIRouter, status, HTTPException

from app.core.config import settings
from app.core.supabase import get_async_admin_supabase
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

START_TIME = time.time()

_DB_CHECK_RETRIES = 3
_DB_CHECK_RETRY_DELAY = 1.0


@router.get("/health")
async def health_check() -> dict:
    """Verify database connectivity asynchronously and expose process uptime."""
    last_exc: Exception | None = None
    error_detail = "database_unreachable"

    for attempt in range(1, _DB_CHECK_RETRIES + 1):
        try:
            sb = await get_async_admin_supabase()
            await sb.table("products").select("id", count="exact").limit(1).execute()
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc).lower()
            if "522" in exc_str or "timeout" in exc_str or "timed out" in exc_str:
                error_detail = "timeout"
            elif "json" in exc_str or "validation" in exc_str:
                error_detail = "invalid_response"
            else:
                error_detail = "database_unreachable"

            if attempt < _DB_CHECK_RETRIES:
                logger.warning(
                    "Health check attempt %d/%d failed (%s): %s — retrying in %.1fs",
                    attempt, _DB_CHECK_RETRIES, error_detail, exc, _DB_CHECK_RETRY_DELAY,
                )
                await asyncio.sleep(_DB_CHECK_RETRY_DELAY)
            else:
                logger.error(
                    "Health check failed after %d attempts (%s): %s",
                    _DB_CHECK_RETRIES, error_detail, exc,
                )

    if last_exc is not None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "Database unreachable", "reason": error_detail},
        )

    return success_response(
        data={
            "status": "ok",
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
            "uptime_seconds": round(time.time() - START_TIME, 2),
            "version": getattr(settings, "APP_VERSION", "1.0.0"),
        }
    )
