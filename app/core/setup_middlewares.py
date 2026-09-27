"""
Middleware Stack Setup
======================
Path: app/core/setup_middlewares.py
"""
from fastapi import FastAPI

from app.api.middlewares.cors import cors_middleware
from app.api.middlewares.csrf import csrf_middleware
from app.api.middlewares.logger import PureWindowLoggerMiddleware
from app.api.middlewares.security import (
    GZipMiddleware,
    HideServerHeaderMiddleware,
    MaxBodySizeMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import SharedRateLimitMiddleware


def apply_middlewares(app: FastAPI) -> None:
    app.middleware("http")(cors_middleware)
    app.middleware("http")(csrf_middleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=10 * 1024 * 1024)
    app.add_middleware(GZipMiddleware, min_size=500, compression_level=6)
    app.add_middleware(HideServerHeaderMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(PureWindowLoggerMiddleware)
    app.add_middleware(SharedRateLimitMiddleware)

