import logging
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 15
_cached_enabled = False
_cached_at = 0.0

# These routes must remain available while the system is in maintenance mode.
_BYPASS_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/settings",
    "/api/v1/settings/",
}


async def maintenance_enabled() -> bool:
    """Read the runtime flag from Supabase with a short process-local cache."""
    global _cached_enabled, _cached_at
    now = time.monotonic()
    if now - _cached_at < _CACHE_TTL_SECONDS:
        return _cached_enabled

    try:
        client = await get_async_admin_supabase()
        result = (
            await client.table("system_settings")
            .select("value,data_type")
            .eq("key", "maintenance_mode")
            .limit(1)
            .execute()
        )
        rows = getattr(result, "data", None) or []
        value: Any = rows[0].get("value") if rows else False
        if isinstance(value, str):
            value = value.strip().lower() in {"1", "true", "yes", "on"}
        _cached_enabled = bool(value)
        _cached_at = now
    except Exception:
        # A settings/database outage must not accidentally take the shop offline.
        logger.exception("Could not read maintenance_mode; failing open")
        _cached_enabled = False
        _cached_at = now

    return _cached_enabled


def invalidate_maintenance_cache() -> None:
    global _cached_at
    _cached_at = 0.0


async def maintenance_middleware(request: Request, call_next):
    path = request.url.path.rstrip("/") or "/"
    if path in _BYPASS_PATHS or path.startswith("/api/v1/auth"):
        return await call_next(request)

    if await maintenance_enabled():
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "code": "MAINTENANCE_MODE",
                "message": "System maintenance mein hai. Please thodi der baad try karein.",
            },
            headers={"Retry-After": "300"},
        )

    return await call_next(request)
