"""
Middleware Stack Setup
======================
Path: app/core/setup_middlewares.py
"""
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.rate_limit import limiter
from app.api.middlewares.security import (
    RequestIDMiddleware, MaxBodySizeMiddleware, GZipMiddleware,
    HideServerHeaderMiddleware, SecurityHeadersMiddleware,
)
from app.api.middlewares.cors import cors_middleware
from app.api.middlewares.logger import PureWindowLoggerMiddleware 

def apply_middlewares(app: FastAPI) -> None:
    """Applies all middlewares to the FastAPI instance in the correct order."""
    
    # 1. CORS — Must be first (preflight handling)
    app.middleware("http")(cors_middleware)
    
    # 2. Request ID & Security
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
    app.add_middleware(GZipMiddleware, min_size=500, compression_level=6)
    app.add_middleware(HideServerHeaderMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    
    # 3. Custom Logger
    app.add_middleware(PureWindowLoggerMiddleware)

    # 4. Global Rate Limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)