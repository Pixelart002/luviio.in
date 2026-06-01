"""
App Factory — main.py
======================
CORS middleware ab middlewares/cors.py mein hai.
"""
import logging
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from postgrest.exceptions import APIError as PostgrestError

from app.config import settings
from app.supabase_client import init_clients, get_admin_supabase
from app.routers import auth, users, products, orders, payments, push
from app.routers import cart,invoice
from app.routers import admin_verify
from app.middlewares.security import (
    HideServerHeaderMiddleware,
    SecurityHeadersMiddleware,
    MaxBodySizeMiddleware,
)
from app.middlewares.cors import cors_middleware   # ← NEW
from app.services.events import register_default_handlers


# ── Log level ────────────────────────────────────────────────────────────────
logging.getLogger("httpx").setLevel(logging.WARNING)

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

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
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

limiter = Limiter(
    key_func=get_real_ip,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

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

# ── Middlewares ───────────────────────────────────────────────────────────────
# CORS — sabse pehle register karo taaki block hone wali requests
# aage ki middlewares tak na pahunchen
app.middleware("http")(cors_middleware)

# Request ID
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

app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(HideServerHeaderMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Routers ──────────────────────────────────────────────────────────────────
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

# ── Exception Handlers ───────────────────────────────────────────────────────
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

# ── Health Check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    try:
        sb = get_admin_supabase()
        sb.table("products").select("id", count="exact").limit(1).execute()
    except Exception as e:
        logger.error("Health check DB ping failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unreachable",
        )
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
