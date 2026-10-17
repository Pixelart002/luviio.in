from __future__ import annotations

import re

import pytest

from app.api.middlewares.security import RequestIDMiddleware
from app.core.logging_config import (
    correlation_id_ctx,
    request_id_ctx,
    span_id_ctx,
    trace_id_ctx,
)


@pytest.mark.asyncio
async def test_request_id_middleware_sets_context_and_response_headers():
    captured = []
    context_seen = {}

    async def app(scope, receive, send):
        context_seen.update({
            "request_id": request_id_ctx.get(),
            "correlation_id": correlation_id_ctx.get(),
            "trace_id": trace_id_ctx.get(),
            "span_id": span_id_ctx.get(),
        })
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/cart",
        "raw_path": b"/api/v1/cart",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        captured.append(message)

    await RequestIDMiddleware(app)(scope, receive, send)

    response_start = next(
        message for message in captured if message["type"] == "http.response.start"
    )
    headers = {key.lower(): value.decode() for key, value in response_start["headers"]}

    assert headers["x-request-id"] == context_seen["request_id"]
    assert headers["x-correlation-id"] == context_seen["correlation_id"]
    assert headers["x-trace-id"] == context_seen["trace_id"]
    assert headers["x-span-id"] == context_seen["span_id"]
    assert headers["x-request-id"]
    assert headers["x-correlation-id"] == headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{32}", headers["x-trace-id"])
    assert re.fullmatch(r"[0-9a-f]{16}", headers["x-span-id"])
    assert request_id_ctx.get() == "-"
    assert correlation_id_ctx.get() == "-"
    assert trace_id_ctx.get() == "-"
    assert span_id_ctx.get() == "-"
