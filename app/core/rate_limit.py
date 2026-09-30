"""Shared API rate limiting.

One enforcement mechanism for the backend: a Postgres-backed token bucket.
The bucket is shared across Koyeb workers and restarts, so rate limiting is
not process-local. Authentication has its own IP/email token buckets in the
auth policy, using the same token-bucket model.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from ipaddress import ip_address, ip_network
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)
ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[Any]], Callable[..., Awaitable[Any]]],
    Awaitable[None],
]
_RATE_LIMIT_RPC_TIMEOUT_SECONDS = 0.35
_LOCAL_FALLBACK_MAX_KEYS = 4096
_LOCAL_FALLBACK_STATE: dict[str, tuple[float, float]] = {}
_LOCAL_FALLBACK_LOCK = asyncio.Lock()


async def _local_fallback_allow(rate_key: str, capacity: int) -> bool:
    """Bounded per-worker emergency token bucket used only when Postgres RPC is unavailable."""
    now = time.monotonic()
    refill = max(capacity, 1) / 60.0
    async with _LOCAL_FALLBACK_LOCK:
        if len(_LOCAL_FALLBACK_STATE) >= _LOCAL_FALLBACK_MAX_KEYS and rate_key not in _LOCAL_FALLBACK_STATE:
            oldest_key = min(_LOCAL_FALLBACK_STATE, key=lambda key: _LOCAL_FALLBACK_STATE[key][0])
            _LOCAL_FALLBACK_STATE.pop(oldest_key, None)
        last, tokens = _LOCAL_FALLBACK_STATE.get(rate_key, (now, float(max(capacity, 1))))
        tokens = min(float(max(capacity, 1)), tokens + max(0.0, now - last) * refill)
        if tokens < 1.0:
            _LOCAL_FALLBACK_STATE[rate_key] = (now, tokens)
            return False
        _LOCAL_FALLBACK_STATE[rate_key] = (now, tokens - 1.0)
        return True


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


def get_client_ip(request: Request) -> str:
    """Return the real client IP only when the immediate proxy is trusted."""
    if _peer_is_trusted(request):
        for header in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
            value = request.headers.get(header)
            if not value:
                continue
            candidate = value.split(",")[0].strip()
            try:
                return str(ip_address(candidate))
            except ValueError:
                continue
    return request.client.host if request.client else "unknown"


class SharedRateLimitMiddleware:
    """Cross-worker global API token-bucket gate backed by Postgres."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.capacity = settings.RATE_LIMIT_PER_MINUTE
        self.refill_seconds = 60

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
        client_ip = get_client_ip(request)
        rate_key = hashlib.sha256(
            f"http:ip:{client_ip}".encode("utf-8")
        ).hexdigest()

        try:
            sb = await get_async_admin_supabase()
            result = await asyncio.wait_for(
                sb.rpc(
                    "consume_http_token_bucket",
                    {
                        "p_rate_key": rate_key,
                        "p_capacity": self.capacity,
                        "p_refill_seconds": self.refill_seconds,
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
        except Exception as exc:
            # Keep bounded local protection during a transient Postgres/RPC
            # outage without emitting noisy emergency-mode warnings.
            allowed = await _local_fallback_allow(rate_key, self.capacity)
            logger.debug(
                "Shared token-bucket unavailable; using local emergency limiter | error_type=%s timeout_s=%s allowed=%s",
                type(exc).__name__,
                _RATE_LIMIT_RPC_TIMEOUT_SECONDS,
                allowed,
            )
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please retry later.",
                    },
                    headers={"Retry-After": "1"},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
