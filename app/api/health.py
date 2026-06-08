"""
Health Check Router
===================
Path: app/api/health.py
"""
import logging
from fastapi import APIRouter, status, HTTPException
from app.core.config import settings
from app.core.supabase import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])

@router.get("/health")
def health_check() -> dict[str, str]:
    """
    Health check endpoint for monitoring and load balancers.
    Verifies database connectivity. Returns 503 if DB is down.
    """
    try:
        sb = get_admin_supabase()
        sb.table("products").select("id", count="exact").limit(1).execute()
    except Exception as exc:
        logger.error("Health check failed — database unreachable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )

    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
    }