"""
Core Logger Configuration
=========================
Path: app/core/logger.py
"""
import logging
from contextvars import ContextVar
from app.core.config import settings

# ── Request ID Context ────────────────────────────────────────────────────────
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

class HealthCheckFilter(logging.Filter):
    """Filter out health check requests from access logs to reduce noise."""
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()

class RequestIDFilter(logging.Filter):
    """Inject request_id into every log record for tracing."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True

def setup_logging():
    """Initialize logging configuration for the application."""
    # Suppress noisy httpx logs in production
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    # Configure root logger
    logging.basicConfig(
        level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
        format="%(asctime)s | %(levelname)s | [%(request_id)s] | %(name)s | %(message)s",
    )

    # Apply request_id filter to all handlers
    _request_filter = RequestIDFilter()
    for handler in logging.root.handlers:
        handler.addFilter(_request_filter)