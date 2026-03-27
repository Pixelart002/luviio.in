"""
App Factory — main.py
======================
CORS: Fully open — any origin, any header, any method, credentials allowed.
"""
import logging
import uuid
from contextvars import ContextVar
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
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
from app.routers import push

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
  ##  docs_url="/docs"            if not settings.is_production else None,
##    redoc_url="/redoc"          if not settings.is_production else None,
##    openapi_url="/openapi.json" if not settings.is_production else None,
   lifespan=lifespan,
)


# ── CORS — Fully open, reflects origin so credentials + any URL works ─────────
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "*")

    if request.method == "OPTIONS":
        return JSONResponse(
            content={},
            status_code=200,
            headers={
                "Access-Control-Allow-Origin":      origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods":     "*",
                "Access-Control-Allow-Headers":     "*",
                "Access-Control-Max-Age":           "86400",
            },
        )

    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"]      = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"]     = "*"
    response.headers["Access-Control-Allow-Headers"]     = "*"
    response.headers["Access-Control-Expose-Headers"]    = "*"
    return response


# ── Request ID ────────────────────────────────────────────────────────────────
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

PREFIX = "/api/v1"
app.include_router(auth.router,     prefix=PREFIX)
app.include_router(users.router,    prefix=PREFIX)
app.include_router(products.router, prefix=PREFIX)
app.include_router(orders.router,   prefix=PREFIX)
app.include_router(payments.router, prefix=PREFIX)
app.include_router(push.router, prefix=PREFIX)


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