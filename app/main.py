"""
App Factory — main.py
======================
FIXES APPLIED:
  1. CORS: allow_credentials=True + allow_origins=["*"] illegal combination fixed
     → Now reflects actual origin when credentials=True
  2. SecurityHeadersMiddleware moved OUTSIDE CORSMiddleware
     → CORS preflight responses no longer get broken CSP headers
  3. Middleware order corrected for proper CORS flow
"""
import logging
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.supabase_client import init_clients, get_admin_supabase
from app.routers import auth, users, products, orders, payments
from app.middlewares.security import (
    HideServerHeaderMiddleware,
    SecurityHeadersMiddleware,
    MaxBodySizeMiddleware,
)
from app.services.events import register_default_handlers

# ── Request ID context ────────────────────────────────────────────────────────
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_ctx.get("-")
        return True


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)s | [%(request_id)s] | %(name)s | %(message)s",
)
_filter = RequestIDFilter()
for handler in logging.root.handlers:
    handler.addFilter(_filter)

logger = logging.getLogger(__name__)


def get_real_ip(request: Request) -> str:
    forwarded_for: str | None = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=get_real_ip)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    init_clients()
    logger.info("Supabase clients initialized")
    register_default_handlers()
    logger.info("Event handlers registered")
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs"            if not settings.is_production else None,
    redoc_url="/redoc"          if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    token = _request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        _request_id_ctx.reset(token)


# ── Middleware order (innermost → outermost, last added = outermost) ──────────
#
# Request flow (outermost first):
#   CORSMiddleware → SecurityHeadersMiddleware → HideServerHeaderMiddleware
#   → MaxBodySizeMiddleware → Route
#
# FIX: CORSMiddleware must be outermost (last added) ✅
# FIX: SecurityHeadersMiddleware is now INSIDE CORSMiddleware
#       → CORS preflight (OPTIONS) is handled by CORS before SecurityHeaders runs
#       → No broken CSP on preflight responses

app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(HideServerHeaderMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# ── CORS — THE MAIN FIX ───────────────────────────────────────────────────────
# BUG: allow_credentials=True + allow_origins=["*"] = browser rejects OPTIONS
# FIX: Use cors_origins from settings (actual domain list, NOT "*")
#      Set ALLOWED_ORIGINS env var on Koyeb:
#        ALLOWED_ORIGINS=https://your-project.vercel.app
#      Multiple domains:
#        ALLOWED_ORIGINS=https://your-project.vercel.app,https://luviio.in
#
# When ALLOWED_ORIGINS is a real domain (not "*"):
#   allow_credentials=True works correctly ✅
#   OPTIONS preflight returns 200 ✅
#   Login/Auth works ✅

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin",
                   "X-Requested-With", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,  # preflight cache 10 min — browser won't re-preflight every time
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

PREFIX = "/api/v1"
app.include_router(auth.router,     prefix=PREFIX)
app.include_router(users.router,    prefix=PREFIX)
app.include_router(products.router, prefix=PREFIX)
app.include_router(orders.router,   prefix=PREFIX)
app.include_router(payments.router, prefix=PREFIX)


@app.exception_handler(PostgrestError)
async def postgrest_error_handler(request: Request, exc: PostgrestError) -> JSONResponse:
    logger.warning("DB error %s: %s", exc.code, exc.message)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if settings.APP_ENV == "development":
        raise exc
    logger.error(
        "Unhandled exception | %s %s | %s",
        request.method, request.url, exc,
        exc_info=True,
    )
    request_id = _request_id_ctx.get("-")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred", "request_id": request_id},
    )


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    try:
        sb = get_admin_supabase()
        sb.table("users").select("id").limit(1).execute()
    except Exception as e:
        logger.error("Health check DB ping failed: %s", e)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )
    return {"status": "ok", "app": settings.APP_NAME}