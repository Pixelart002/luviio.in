"""
Core Logger Configuration
=========================
Path: app/core/logger.py
"""
import logging
from contextvars import ContextVar
from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()

class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True

def setup_logging():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())

    logging.basicConfig(
        level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO,
        format="%(asctime)s | %(levelname)s | [%(request_id)s] | %(name)s | %(message)s",
    )

    req_filter = RequestIDFilter()
    for handler in logging.root.handlers:
        handler.addFilter(req_filter)