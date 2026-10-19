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


def test_production_wildcard_falls_back_to_exact_luviio_origins(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.luviio.in/store/")

    origins = settings.cors_origins

    assert "https://www.luviio.in" in origins
    assert "https://luviio.in" in origins
    assert "*" not in origins
    assert csrf_origin_allowed("https://www.luviio.in") is True
    assert csrf_origin_allowed("https://luviio.in") is True
    assert csrf_origin_allowed("https://attacker.example") is False


def test_production_cors_allows_frontend_when_deployed_allowlist_is_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "*")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.luviio.in")

    async def run():
        async def call_next(_request):
            return Response("ok")

        return await cors_middleware(_request("https://www.luviio.in"), call_next)

    response = asyncio.run(run())

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://www.luviio.in"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_production_cors_normalizes_explicit_origin_trailing_slash(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(
        settings,
        "ALLOWED_ORIGINS",
        "https://luviio.in/,https://www.luviio.in/",
    )

    origins = settings.cors_origins

    assert "https://luviio.in" in origins
    assert "https://www.luviio.in" in origins



def test_production_allows_exact_vercel_frontend_origin_for_cors_and_csrf(monkeypatch):
    vercel_origin = "https://my-frontend-e4v9utdl8-pixelart002s-projects.vercel.app"
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://luviio.in,https://www.luviio.in")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://www.luviio.in")

    assert vercel_origin in settings.cors_origins
    assert csrf_origin_allowed(vercel_origin) is True
    assert csrf_origin_allowed("https://untrusted-preview.vercel.app") is False

    async def run():
        async def call_next(_request):
            return Response("ok")

        return await cors_middleware(_request(vercel_origin), call_next)

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == vercel_origin
    assert response.headers.get("access-control-allow-credentials") == "true"
