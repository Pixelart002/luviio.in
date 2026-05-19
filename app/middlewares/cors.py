"""
middlewares/cors.py
===================
CORS Middleware — production mein sirf whitelisted origins allow karta hai.
Unknown origins ko 403 milta hai (pehle 200 milta tha — FIX).
"""
import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed_origins = settings.cors_origins  # list from config.py

    # ── Determine if origin is allowed ──────────────────────────────
    # Dev mode  : sab allow
    # Prod mode : sirf whitelisted origins; no-origin requests (curl,
    #             server-to-server) allowed — unpar CORS apply nahi hota
    if not settings.is_production:
        allowed = True
        final_origin = origin or "*"

    elif origin is None:
        # No Origin header → browser CORS request nahi → allow, par
        # Access-Control-Allow-Origin header mat bhejo
        allowed = True
        final_origin = None

    elif origin in allowed_origins:
        allowed = True
        final_origin = origin

    else:
        # Production mein unknown origin → block
        allowed = False
        final_origin = None

    # ── Block non-whitelisted origins ───────────────────────────────
    if not allowed:
        logger.warning(
            "CORS blocked: origin=%s  path=%s", origin, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "CORS: origin not allowed"},
        )

    # ── Preflight (OPTIONS) ─────────────────────────────────────────
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Max-Age": "86400",
        }
        if final_origin:
            headers["Access-Control-Allow-Origin"] = final_origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(content={}, status_code=200, headers=headers)

    # ── Normal request ──────────────────────────────────────────────
    response = await call_next(request)
    if final_origin:
        response.headers["Access-Control-Allow-Origin"] = final_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
