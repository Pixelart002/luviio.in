"""Low-overhead request logging middleware.

Keeps request state/context available to the application, but avoids building
large ANSI/PII-heavy log payloads on every request. Only errors and slow
requests are emitted at INFO/WARNING level.
"""
import logging
import time
from typing import Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import current_request_ctx

logger = logging.getLogger("uvicorn.error")


class PureWindowLoggerMiddleware(BaseHTTPMiddleware):
    """Minimal request telemetry with bounded work on the hot path."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method == "OPTIONS" or request.url.path in {"/health", "/metrics"}:
            return await call_next(request)

        context_token = current_request_ctx.set(request)
        request.state.user_name = "Guest (Unauthenticated)"
        request.state.user_id = "N/A"
        request.state.actions = []
        started = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            logger.exception(
                "request_unhandled_error method=%s path=%s",
                request.method,
                request.url.path,
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            # Never log email, name, IP, Origin, user-agent, cookies,
            # authorization headers, request bodies, or action strings.
            if status_code >= 500:
                logger.error(
                    "request_failed method=%s path=%s status=%s duration_ms=%.2f",
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                )
            elif status_code >= 400:
                logger.warning(
                    "request_rejected method=%s path=%s status=%s duration_ms=%.2f",
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                )
            elif duration_ms >= 1000:
                logger.warning(
                    "request_slow method=%s path=%s status=%s duration_ms=%.2f",
                    request.method,
                    request.url.path,
                    status_code,
                    duration_ms,
                )
            current_request_ctx.reset(context_token)


__all__ = ["PureWindowLoggerMiddleware"]
