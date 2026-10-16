from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.middlewares.csrf import csrf_middleware
from app.core.config import settings


def _request(method: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/api/v1/auth/refresh",
            "raw_path": b"/api/v1/auth/refresh",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
        }
    )


@pytest.fixture(autouse=True)
def trusted_origins(monkeypatch):
    monkeypatch.setattr(
        settings,
        "ALLOWED_ORIGINS",
        "https://luviio.in,https://www.luviio.in",
    )


@pytest.mark.asyncio
async def test_cookie_mutation_with_trusted_origin_is_allowed():
    request = _request(
        "POST",
        [
            (b"cookie", b"refresh_token=opaque"),
            (b"origin", b"https://www.luviio.in"),
        ],
    )
    called = False

    async def call_next(_request):
        nonlocal called
        called = True
        return Response("ok")

    response = await csrf_middleware(request, call_next)

    assert response.status_code == 200
    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        [(b"cookie", b"refresh_token=opaque")],
        [
            (b"cookie", b"refresh_token=opaque"),
            (b"origin", b"https://attacker.example"),
        ],
    ],
)
async def test_cookie_mutation_without_trusted_origin_is_rejected(headers):
    request = _request("POST", headers)

    async def call_next(_request):
        pytest.fail("CSRF middleware must reject this request before routing")

    response = await csrf_middleware(request, call_next)

    assert response.status_code == 403
    assert response.body == b'{"detail":"CSRF validation failed."}'


@pytest.mark.asyncio
async def test_cookie_mutation_accepts_trusted_referer_fallback():
    request = _request(
        "POST",
        [
            (b"cookie", b"refresh_token=opaque"),
            (b"referer", b"https://luviio.in/account"),
        ],
    )

    async def call_next(_request):
        return Response("ok")

    response = await csrf_middleware(request, call_next)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_bearer_request_does_not_depend_on_cookie_csrf_check():
    request = _request(
        "POST",
        [
            (b"cookie", b"refresh_token=opaque"),
            (b"authorization", b"Bearer test-token"),
            (b"origin", b"https://attacker.example"),
        ],
    )

    async def call_next(_request):
        return Response("ok")

    response = await csrf_middleware(request, call_next)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_safe_request_does_not_require_origin():
    request = _request("GET", [(b"cookie", b"refresh_token=opaque")])

    async def call_next(_request):
        return Response("ok")

    response = await csrf_middleware(request, call_next)

    assert response.status_code == 200
