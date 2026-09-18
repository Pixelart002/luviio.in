"""
Global Rate Limiter
===================
Path: app/core/rate_limit.py

Client-IP extraction is kept separate from the enforcement layer. The global
API ceiling is enforced through a service-role-only Postgres RPC so multiple
Koyeb workers share the same counter. SlowAPI remains available for the
existing endpoint-specific limits.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from ipaddress import ip_address, ip_network
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter

from app.core.config import settings
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)
ASGIApp = Callable[[dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]], Awaitable[None]]
_RATE_LIMIT_RPC_TIMEOUT_SECONDS = 0.75


def _peer_is_trusted(request: Request) -> bool:
    peer = request.client.host if request.client else ""
    if not peer:
        return False

    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return False

    for entry in settings.trusted_proxy_ips:
        try:
            if "/" in entry:
                if peer_ip in ip_network(entry, strict=False):
                    return True
            elif peer_ip == ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def _get_client_ip(request: Request) -> str:
    if _peer_is_trusted(request):
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            try:
                return str(ip_address(cf_ip.strip()))
            except ValueError:
                pass

        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                pass

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            try:
                return str(ip_address(real_ip.strip()))
            except ValueError:
                pass

    return request.client.host if request.client else "unknown"


# Endpoint-specific decorators still use SlowAPI. The global ceiling is
# enforced by SharedRateLimitMiddleware below and is intentionally removed
# from SlowAPI's default_limits to avoid two independent global counters.
limiter = Limiter(key_func=_get_client_ip, default_limits=[])


class SharedRateLimitMiddleware:
    """Cross-worker global API rate-limit gate backed by Postgres."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.limit = settings.RATE_LIMIT_PER_MINUTE
        self.window_seconds = 60

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[Any]],
        send: Callable[..., Awaitable[Any]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if not path.startswith("/api/v1") or method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        client_ip = _get_client_ip(request)
        key = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()

        try:
            sb = await get_async_admin_supabase()
            result = await asyncio.wait_for(
                sb.rpc(
                    "consume_http_rate_limit",
                    {
                        "p_rate_key": key,
                        "p_limit": self.limit,
                        "p_window_seconds": self.window_seconds,
                    },
                ).execute(),
                timeout=_RATE_LIMIT_RPC_TIMEOUT_SECONDS,
            )
            data = result.data
            if isinstance(data, list):
                data = data[0] if data else None
            if not isinstance(data, dict) or not data.get("allowed"):
                retry_after = int((data or {}).get("retry_after_seconds", 1))
                response = JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please retry later.",
                    },
                    headers={"Retry-After": str(max(1, retry_after))},
                )
                await response(scope, receive, send)
                return
        except asyncio.TimeoutError:
            # Rate limiting is a protection layer, not a dependency of the
            # shop itself. Do not let a slow Supabase RPC turn every request
            # into a multi-second/503 outage.
            logger.warning(
                "Shared rate-limit RPC timed out; allowing request | timeout_s=%s",
                _RATE_LIMIT_RPC_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            # The endpoint-specific SlowAPI limits remain active. Failing open
            # here keeps the application available when the shared limiter's
            # database connection is unhealthy.
            logger.warning(
                "Shared rate-limit state unavailable; allowing request | error_type=%s",
                type(exc).__name__,
            )

        await self.app(scope, receive, send)
