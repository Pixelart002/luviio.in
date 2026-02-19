import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.db.client import get_supabase_client
from app.routes import home, auth

# Setup structured logging
setup_logging()
logger = logging.getLogger("luviio")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Luviio...")
    # Test Supabase connection using a thread to avoid blocking
    try:
        client = get_supabase_client()
        # Run the synchronous query in a thread pool
        await asyncio.to_thread(
            lambda: client.table("health_check").select("*").limit(1).execute()
        )
        logger.info("Supabase connection OK")
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        # App continues but with degraded functionality
    yield
    logger.info("Shutting down Luviio.")

def create_app() -> FastAPI:
    app = FastAPI(
        title="Luviio Studio",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url=None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Trusted host middleware
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS
    )

    # Session middleware (requires itsdangerous)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET
    )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com;"
        )
        return response

    # Global exception handler with AI debugger
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:8]
        logger.exception(f"Unhandled exception {error_id}: {exc}")

        ai_suggestion = ""
        if settings.ENVIRONMENT == "development" and settings.AI_DEBUGGER_URL:
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(
                        f"{settings.AI_DEBUGGER_URL}{exc}"
                    )
                    if resp.status_code == 200:
                        ai_suggestion = resp.text[:200]
            except Exception:
                pass

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "error_id": error_id,
                "ai_suggestion": ai_suggestion if ai_suggestion else None,
            },
        )

    # Jinja2 templates setup
    templates = Jinja2Templates(directory="app/templates")
    templates.env.enable_async = True
    templates.env.globals["settings"] = settings

    # Include routers
    app.include_router(home.router, tags=["pages"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])

    # Middleware to inject templates into request state
    @app.middleware("http")
    async def add_templates_to_request(request: Request, call_next):
        request.state.templates = templates
        return await call_next(request)

    return app

# Vercel entry point
app = create_app()