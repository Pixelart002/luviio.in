"""
Auth HTTP Client Lifecycle
==========================
Path: app/domains/auth/http_client.py

Process-scoped HTTP client for outbound Supabase Auth requests.
The client is shared across auth requests so keep-alive connections can be
reused instead of creating a new TCP/TLS pool for every request.
"""
from __future__ import annotations

import httpx


_auth_http_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=50,
        max_keepalive_connections=20,
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(10.0, connect=3.0)
    return httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        follow_redirects=False,
    )


async def init_auth_http_client() -> httpx.AsyncClient:
    """Create the process-scoped auth HTTP client once."""
    global _auth_http_client
    if _auth_http_client is None or _auth_http_client.is_closed:
        _auth_http_client = _build_client()
    return _auth_http_client


async def get_auth_http_client() -> httpx.AsyncClient:
    """Return the shared auth HTTP client, lazily initializing it when needed."""
    return await init_auth_http_client()


async def close_auth_http_client() -> None:
    """Close the shared auth HTTP client during application shutdown."""
    global _auth_http_client
    client = _auth_http_client
    _auth_http_client = None
    if client is not None and not client.is_closed:
        await client.aclose()
