from __future__ import annotations

import pytest

from app.api.middlewares.security import SecurityHeadersMiddleware


async def _response_headers(path: str, initial_headers: list[tuple[bytes, bytes]] | None = None):
    captured = []

    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": initial_headers or [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = SecurityHeadersMiddleware(app)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        captured.append(message)

    await middleware(scope, receive, send)
    start = next(message for message in captured if message["type"] == "http.response.start")
    return {key.lower(): value for key, value in start["headers"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "/api/v1/cart",
    "/api/v1/orders/my",
    "/api/v1/admin/users",
    "/api/v1",
])
async def test_api_responses_are_private_and_not_stored(path):
    headers = await _response_headers(
        path,
        [
            (b"content-type", b"application/json"),
            (b"cache-control", b"public, max-age=3600"),
            (b"pragma", b"public"),
        ],
    )

    assert headers[b"cache-control"] == b"private, no-store, max-age=0, must-revalidate"
    assert headers[b"pragma"] == b"no-cache"
    assert headers[b"expires"] == b"0"


@pytest.mark.asyncio
async def test_non_api_cache_policy_is_not_overridden():
    headers = await _response_headers(
        "/health/live",
        [
            (b"content-type", b"application/json"),
            (b"cache-control", b"public, max-age=300"),
        ],
    )

    assert headers[b"cache-control"] == b"public, max-age=300"
