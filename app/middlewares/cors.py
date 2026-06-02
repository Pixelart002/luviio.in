"""
CORS Middleware — Production Grade
===================================
Handles Cross-Origin Resource Sharing with strict whitelisting.

SECURITY:
  • Production: Only whitelisted origins allowed → 403 for others
  • Development: All origins allowed (for local testing)
  • Server-to-server: No Origin header = allowed (not a browser request)
  • Preflight: Proper OPTIONS handling with caching

FIXES:
  1. Unknown origins → 403 (was 200 — security hole)
  2. No-Origin requests properly handled (curl, Postman, server-to-server)
  3. Credentials support for cookie-based auth
  4. Preflight caching (24h) to reduce OPTIONS requests

ARCHITECTURE:
  Browser Request (Origin: https://luviio.in)
      ↓
  Check: Is origin in ALLOWED_ORIGINS?
      ↓ YES → Allow, add CORS headers
      ↓ NO  → 403 Forbidden
      
  Server-to-Server (No Origin header)
      ↓
  Allow, but don't add CORS headers (browser not involved)
"""
import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)


async def cors_middleware(request: Request, call_next):
    """
    CORS middleware with strict origin checking.
    
    Flow:
      1. Extract Origin header
      2. Determine if origin is allowed
      3. Block (403) or allow with proper CORS headers
      4. Handle preflight (OPTIONS) requests
    
    Returns:
        Response with appropriate CORS headers
    """
    origin = request.headers.get("origin")
    allowed_origins = settings.cors_origins  # List from config

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 1: Determine if origin is allowed
    # ══════════════════════════════════════════════════════════════════════════
    
    if not settings.is_production:
        # ── Development mode: Allow all origins ───────────────────────────────
        allowed = True
        final_origin = origin or "*"

    elif origin is None:
        # ── No Origin header: Server-to-server request ────────────────────────
        # Examples: curl, Postman, Python requests, webhooks, microservices
        # These are NOT browser CORS requests — allow them
        # Don't add Access-Control-Allow-Origin (browser not involved)
        allowed = True
        final_origin = None

    elif origin in allowed_origins:
        # ── Whitelisted origin: Browser request from allowed domain ───────────
        allowed = True
        final_origin = origin

    else:
        # ── Unknown origin: Block with 403 ────────────────────────────────────
        # This could be:
        #   • Malicious site trying to access our API
        #   • Forgotten domain that needs to be added to ALLOWED_ORIGINS
        #   • Typo in the origin
        allowed = False
        final_origin = None

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 2: Block if not allowed
    # ══════════════════════════════════════════════════════════════════════════
    
    if not allowed:
        logger.warning(
            "CORS BLOCKED | origin=%s method=%s path=%s",
            origin, request.method, request.url.path
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": "Origin not allowed. Contact support if you believe this is an error.",
            },
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 3: Handle preflight (OPTIONS) requests
    # ══════════════════════════════════════════════════════════════════════════
    
    if request.method == "OPTIONS":
        # Preflight request — browser checks if CORS is allowed before actual request
        
        preflight_headers = {
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, Authorization, X-Requested-With, "
                "X-Request-ID, Accept, Accept-Language, Cache-Control"
            ),
            "Access-Control-Max-Age": "86400",  # Cache preflight for 24 hours
        }
        
        if final_origin:
            preflight_headers["Access-Control-Allow-Origin"] = final_origin
            preflight_headers["Access-Control-Allow-Credentials"] = "true"
            # Echo back the requested headers if present
            requested_headers = request.headers.get("Access-Control-Request-Headers")
            if requested_headers:
                preflight_headers["Access-Control-Allow-Headers"] = requested_headers
        
        return JSONResponse(
            content={"message": "Preflight OK"},
            status_code=200,
            headers=preflight_headers,
        )

    # ══════════════════════════════════════════════════════════════════════════
    #  STEP 4: Normal request — add CORS headers to response
    # ══════════════════════════════════════════════════════════════════════════
    
    response = await call_next(request)
    
    if final_origin:
        response.headers["Access-Control-Allow-Origin"] = final_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        # Expose custom headers to frontend
        response.headers["Access-Control-Expose-Headers"] = (
            "X-Request-ID, Content-Disposition, X-RateLimit-Limit, "
            "X-RateLimit-Remaining, X-RateLimit-Reset"
        )
    
    return response