"""
Health Check Router — Async Enterprise Grade
============================================
Path: app/api/v1/routers/health.py
"""
import logging
import time
from fastapi import APIRouter, status, HTTPException

from app.core.config import settings
from app.core.supabase import get_async_admin_supabase
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

START_TIME = time.time()

@router.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint for monitoring and load balancers.
    Verifies database connectivity asynchronously. Returns 503 if DB is down.
    """
    try:
        # 🔥 FIX: Awaiting async client factory
        sb = await get_async_admin_supabase()
        
        # Lightweight check: selecting count from a known table
        await sb.table("products").select("id", count="exact").limit(1).execute()
        
    except Exception as exc:
        logger.error("Health check failed — database unreachable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )

    uptime = round(time.time() - START_TIME, 2)
    
    return success_response(
        data={
            "status": "ok",
            "app": settings.APP_NAME,
            "env": settings.APP_ENV,
            "uptime_seconds": uptime,
            "version": getattr(settings, "APP_VERSION", "1.0.0") # Optional: add versioning
        }
    )