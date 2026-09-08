"""Structured, redacted logging and request correlation helpers."""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")
trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="-")
span_id_ctx: ContextVar[str] = ContextVar("span_id", default="-")

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SECRET_KEYS = re.compile(r"authorization|cookie|token|secret|password|api[_-]?key|card|cvv|private", re.I)


def safe_id(value: str | None) -> str:
    value = (value or "").strip()
    return value if _SAFE_ID.fullmatch(value) else str(uuid.uuid4())


def new_id() -> str:
    return str(uuid.uuid4())


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_KEYS.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.correlation_id = correlation_id_ctx.get()
        record.trace_id = trace_id_ctx.get()
        record.span_id = span_id_ctx.get()
        record.user_id = getattr(record, "user_id", "-")
        return True


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return (
            f"{datetime.now(timezone.utc).isoformat(timespec='milliseconds')} | "
            f"{record.levelname:<8} | req={record.request_id} corr={record.correlation_id} "
            f"trace={record.trace_id} | {record.name} | {record.getMessage()}"
        )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": record.request_id,
            "correlation_id": record.correlation_id,
            "trace_id": record.trace_id,
            "span_id": record.span_id,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_luviio_configured", False):
        return
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if os.getenv("APP_ENV", "production") == "production" else PrettyFormatter())
    handler.addFilter(ContextFilter())
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    root._luviio_configured = True


__all__ = ["configure_logging", "correlation_id_ctx", "new_id", "request_id_ctx", "safe_id", "span_id_ctx", "trace_id_ctx"]
