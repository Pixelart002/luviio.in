"""Regression tests for production CORS/CSRF wildcard handling."""

import asyncio

from starlette.requests import Request
from starlette.responses import Response

from app.api.middlewares.cors import cors_middleware
from app.api.middlewares.csrf import _allowed as csrf_origin_allowed
from app.core.config import settings


def _request(origin: str) -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/products",
            "raw_path": b"/api/v1/products",
            "query_string": b"",
            "headers": [(b"origin", origin.encode("latin-1"))],
            "client": ("testclient", 12345),
            "server": ("testserver", 443),
        }
    )


def test_production_csrf_does_not_treat_wildcard_as_trusted(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")

    assert csrf_origin_allowed("https://evil.example") is False


def test_production_csrf_accepts_exact_allowlisted_origin(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(
        settings, "ALLOWED_ORIGINS", "https://www.luviio.in,https://luviio.in"
    )

    assert csrf_origin_allowed("https://www.luviio.in") is True
    assert csrf_origin_allowed("https://evil.example") is False


def test_production_cors_rejects_wildcard_configuration(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")

    async def run():
        async def call_next(_request):
            return Response("should not be reached")

        return await cors_middleware(_request("https://evil.example"), call_next)

    response = asyncio.run(run())
    assert response.status_code == 403
    assert response.headers.get("access-control-allow-origin") == "null"
