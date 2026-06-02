"""
Luviio — FastAPI Application Factory
=====================================
main.py: Application entry point, middleware stack, and lifecycle management.

Architecture:
  • Lifespan: init clients → register event handlers → graceful shutdown
  • Middleware: CORS → RequestID → MaxBody → GZip → HideServer → Security → RateLimit
  • Routers: Modular, prefixed with /api/v1
  • Error handling: Structured, never leaks internals in production

To run:
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.supabase_client import init_clients, get_admin_supabase

# Routers
from app.routers import auth, users, products, orders, payments, push
from app.routers import cart, invoice, admin_verify

# Middleware
from app.middlewares.security import (
    RequestIDMiddleware,
    MaxBodySizeMiddleware,
    GZipMiddleware,
    HideServerHeaderMiddleware,
    SecurityHeadersMiddleware,
)
from app.middlewares.cors import cors_middleware

# Services
from app.services.events import register_default_handlers


# ══════════════════════════════════════════════════════════════════════════════
#  LOGGING SETUP
# ══════════════════════════════════════════════════════════════════════════════

# Suppress noisy httpx logs in production
logging.getLogger("httpx").setLevel(logging.WARNING)


class HealthCheckFilter(logging.Filter):
    """Filter out health check requests from access logs to reduce noise."""
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


# ── Request ID Context ────────────────────────────────────────────────────────
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """Inject request_id into every log record for tracing."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get("-")
        return True


# Configure root logger
logging.basicConfig(
    level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)s | [%(request_id)s] | %(name)s | %(message)s",
)

# Apply request_id filter to all handlers
_request_filter = RequestIDFilter()
for handler in logging.root.handlers:
    handler.addFilter(_request_filter)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

def _get_client_ip(request: Request) -> str:
    """
    Extract real client IP considering proxy headers.
    Checks: X-Forwarded-For → X-Real-IP → CF-Connecting-IP → direct.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  LIFESPAN — Startup & Shutdown
# ══════════════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle:
      Startup:  Initialize Supabase clients, register event handlers
      Shutdown: Cleanup resources gracefully
    """
    logger.info("🚀 Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)

    # Initialize Supabase clients (admin + public)
    init_clients()

    # Register event handlers (push notifications, emails)
    register_default_handlers()

    logger.info("✅ Application ready")

    yield  # Application runs here

    logger.info("👋 Shutting down %s", settings.APP_NAME)


# ══════════════════════════════════════════════════════════════════════════════
#  FASTAPI APP
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs" if settings.APP_ENV == "production" else None,
    redoc_url="/redoc" if settings.APP_ENV == "development" else None,
    openapi_url="/openapi.json" if settings.APP_ENV == "development" else None,
    lifespan=lifespan,
)


# ══════════════════════════════════════════════════════════════════════════════
#  MIDDLEWARE STACK (Order Matters!)
# ══════════════════════════════════════════════════════════════════════════════
#
#  Request Flow:
#    1. CORS          → Preflight handling, origin whitelisting
#    2. RequestID     → Unique ID for tracing (logs + response header)
#    3. MaxBodySize   → Reject oversized requests (anti-DoS)
#    4. GZip          → Compress JSON responses (bandwidth savings)
#    5. HideServer    → Mask server signature
#    6. Security      → Security headers (HSTS, X-Frame, etc.)
#    7. Rate Limiter  → Per-minute request limits
#
# ══════════════════════════════════════════════════════════════════════════════

# 1. CORS — Must be first (preflight handling)
app.middleware("http")(cors_middleware)

# 2. Request ID — Tracing (now as proper ASGI middleware)
app.add_middleware(RequestIDMiddleware)

# 3. Max Body Size — DoS protection
app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)

# 4. GZip Compression — Reduce response size by 50-80%
app.add_middleware(GZipMiddleware, min_size=500, compression_level=6)

# 5. Hide Server Header — Prevent fingerprinting
app.add_middleware(HideServerHeaderMiddleware)

# 6. Security Headers — HSTS, X-Frame-Options, etc.
app.add_middleware(SecurityHeadersMiddleware)

# 7. Rate Limiter — Global rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTERS — Modular & Prefixed
# ══════════════════════════════════════════════════════════════════════════════

PREFIX = "/api/v1"

app.include_router(auth.router,         prefix=PREFIX)
app.include_router(users.router,        prefix=PREFIX)
app.include_router(products.router,     prefix=PREFIX)
app.include_router(orders.router,       prefix=PREFIX)
app.include_router(payments.router,     prefix=PREFIX)
app.include_router(push.router,         prefix=PREFIX)
app.include_router(admin_verify.router, prefix=PREFIX)
app.include_router(cart.router,         prefix=PREFIX)
app.include_router(invoice.router,      prefix=PREFIX)


# ══════════════════════════════════════════════════════════════════════════════
#  EXCEPTION HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@app.exception_handler(PostgrestError)
async def postgrest_error_handler(
    request: Request,
    exc: PostgrestError,
) -> JSONResponse:
    """Handle Supabase/PostgREST errors gracefully."""
    logger.warning(
        "Database error | code=%s message=%s | %s %s",
        exc.code, exc.message, request.method, request.url.path
    )
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handle known HTTP exceptions with request ID."""
    request_id = _request_id_ctx.get("-")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "request_id": request_id,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Catch-all handler for unhandled exceptions.
    Development: Re-raise for debugging
    Production:  Return generic 500 with request_id for support
    """
    if settings.APP_ENV == "development":
        raise exc

    request_id = _request_id_ctx.get("-")
    logger.error(
        "Unhandled exception | request_id=%s | %s %s | %s",
        request_id, request.method, request.url.path, exc,
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. Please try again.",
            "request_id": request_id,
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/health", tags=["Health"])
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