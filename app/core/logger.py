"""
Core Logger Configuration
=========================
Path: app/core/logger.py

UPGRADE: Added `current_request_ctx` bridge and User attribution 
attributes (`user_id`, `user_name`) to `RequestIDFilter` without breaking 
a single existing `request_id_ctx` import in your app.
"""
import logging
from typing import Any, Optional
from contextvars import ContextVar
from app.core.config import settings

# 1. Existing Request ID context (Preserved 100%)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# 2. 🔥 NEW: Active Starlette Request context bridge for Middleware
current_request_ctx: ContextVar[Optional[Any]] = ContextVar("current_request", default=None)


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # ── 1. Existing Request ID capture (Untouched) ──
        record.request_id = request_id_ctx.get("-")

        # ── 2. 🔥 NEW: Safely extract User info from the running Request ──
        req = current_request_ctx.get()
        state = getattr(req, "state", None) if req else None

        record.user_id = getattr(state, "user_id", "anon") if state else "anon"
        record.user_name = getattr(state, "user_name", "Guest") if state else "Guest"
        return True


def setup_logging():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    logging.basicConfig(
        level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
        # 🔥 FORMAT STRING UPGRADED: Added [%(user_id)s : %(user_name)s]
        format="%(asctime)s | %(levelname)s | [%(request_id)s] | [%(user_id)s : %(user_name)s] | %(name)s | %(message)s",
    )

    req_filter = RequestIDFilter()
    for handler in logging.root.handlers:
        handler.addFilter(req_filter)