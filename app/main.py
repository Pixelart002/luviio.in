"""
App Factory — main.py
======================
CORS: Controlled via Settings (ALLOWED_ORIGINS). 
Reflects origin ONLY if it's in the whitelist for security.
"""
import logging
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.supabase_client import init_clients, get_admin_supabase
from app.routers import auth, users, products, orders, payments, push
from app.routers import admin_verify
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

# ── Rate Limiter ─────────────────────────────────────────────────────────────
def get_real_ip(request: Request) -> str:
    forwarded_for: str | None = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() # Take the first IP in the list
    return request.client.host if request.client else "unknown"

limiter = Limiter(key_func=get_real_ip, default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"])

# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    init_clients()
    register_default_handlers()
    yield
    logger.info("Shutting down %s", settings.APP_NAME)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS Middleware ─────────────────────────────────────────────────────────
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    # Determine the origin to allow
    origin = request.headers.get("origin")
    allowed_origins = settings.cors_origins # List from config.py

    # Logic: If origin is in our whitelist OR we are in dev mode with "*"
    final_origin = "*"
    if not settings.is_production:
        final_origin = origin or "*"
    elif origin in allowed_origins:
        final_origin = origin

    if request.method == "OPTIONS":
        return JSONResponse(
            content={},
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": final_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
                "Access-Control-Max-Age": "86400",
            },
        )

    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = final_origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# ── Request ID Middleware ───────────────────────────────────────────────────
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

# ── Other Middlewares ───────────────────────────────────────────────────────
app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(HideServerHeaderMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiter Setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Routers ──────────────────────────────────────────────────────────────────
PREFIX = "/api/v1"
app.include_router(auth.router,     prefix=PREFIX)
app.include_router(users.router,    prefix=PREFIX)
app.include_router(products.router, prefix=PREFIX)
app.include_router(orders.router,   prefix=PREFIX)
app.include_router(payments.router, prefix=PREFIX)
app.include_router(push.router,     prefix=PREFIX)
app.include_router(admin_verify.router, prefix=PREFIX)

# ── Exception Handlers ──────────────────────────────────────────────────────
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
    
    logger.error(f"Unhandled exception | {request.method} {request.url} | {exc}", exc_info=True)
    request_id = _request_id_ctx.get("-")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred", "request_id": request_id},
    )

# ── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    try:
        sb = get_admin_supabase()
        # Use a more generic query for health check
        sb.table("products").select("id", count="exact").limit(1).execute()
    except Exception as e:
        logger.error("Health check DB ping failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}