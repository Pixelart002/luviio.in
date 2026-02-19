import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.security import add_security_headers
from app.db.client import supabase_client
from app.routes import home, auth

# Setup structured logging
setup_logging()
logger = logging.getLogger("luviio")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify Supabase connection
    logger.info("Starting Luviio...")
    try:
        # Simple health check
        await supabase_client.table("health_check").select("*").limit(1).execute()
        logger.info("Supabase connection OK")
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
    yield
    # Shutdown
    logger.info("Shutting down Luviio.")

def create_app() -> FastAPI:
    app = FastAPI(
        title="Luviio Studio",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.ENVIRONMENT == "development" else None,
        redoc_url=None,
    )

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
    app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)
    app.middleware("http")(add_security_headers)

    # Exception handler with AI debugger
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:8]
        logger.exception(f"Unhandled exception {error_id}: {exc}")

        # Call AI debugger (async, but don't block response)
        ai_suggestion = ""
        if settings.ENVIRONMENT == "development":
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    resp = await client.get(
                        f"{settings.AI_DEBUGGER_URL}{exc}"
                    )
                    if resp.status_code == 200:
                        ai_suggestion = resp.text[:200]
            except:
                pass

        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "error_id": error_id,
                "ai_suggestion": ai_suggestion if ai_suggestion else None,
            },
        )

    # Templates
    templates = Jinja2Templates(directory="app/templates")
    templates.env.enable_async = True
    # Make settings available in templates
    templates.env.globals["settings"] = settings

    # Include routers
    app.include_router(home.router, tags=["pages"])
    app.include_router(auth.router, prefix="/auth", tags=["auth"])

    # Inject templates into request state for routes
    @app.middleware("http")
    async def add_templates_to_request(request: Request, call_next):
        request.state.templates = templates
        return await call_next(request)

    return app

app = create_app()