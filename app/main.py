import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.supabase_client import init_clients
from app.routers import auth, users, products, orders, payments
from app.middlewares.security import (
    HideServerHeaderMiddleware,
    SecurityHeadersMiddleware,
    MaxBodySizeMiddleware,
)

logging.basicConfig(
    level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Real IP — proxy-aware ─────────────────────────────────────────────────────
def get_real_ip(request: Request) -> str:
    """
    Koyeb/Nginx ke peeche: X-Forwarded-For ka LAST value use karo.
    Last value proxy ka add kiya hua hota hai — attacker fake nahi kar sakta.
    Format: X-Forwarded-For: client, proxy1, proxy2 (last = proxy-added)
    """
    forwarded_for: str | None = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


# ── Request ID middleware ─────────────────────────────────────────────────────
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Har request ko unique ID deta hai — logs trace karne ke liye."""
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


limiter = Limiter(key_func=get_real_ip)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s [%s]", settings.APP_NAME, settings.APP_ENV)
    init_clients()
    logger.info("Supabase clients initialized")
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs"        if not settings.is_production else None,
    redoc_url="/redoc"      if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# Middleware order: outermost → innermost (first added = last executed)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
app.add_middleware(HideServerHeaderMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "stripe-signature"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

PREFIX = "/api/v1"
app.include_router(auth.router,     prefix=PREFIX)
app.include_router(users.router,    prefix=PREFIX)
app.include_router(products.router, prefix=PREFIX)
app.include_router(orders.router,   prefix=PREFIX)
app.include_router(payments.router, prefix=PREFIX)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if settings.APP_ENV == "development":
        raise exc
    request_id: str = getattr(request.state, "request_id", "unknown")
    logger.error(
        "[%s] Unhandled exception | %s %s | %s",
        request_id, request.method, request.url, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred", "request_id": request_id},
    )


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.APP_NAME}