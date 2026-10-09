import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import rate_limit


def _client_with_rpc(monkeypatch, rpc_result=None, rpc_error=None):
    supabase = MagicMock()
    if rpc_error is not None:
        supabase.rpc.return_value.execute = AsyncMock(side_effect=rpc_error)
    else:
        supabase.rpc.return_value.execute = AsyncMock(
            return_value=SimpleNamespace(data=rpc_result)
        )
    monkeypatch.setattr(
        rate_limit,
        "get_async_admin_supabase",
        AsyncMock(return_value=supabase),
    )

    app = FastAPI()
    app.add_middleware(rate_limit.SharedRateLimitMiddleware)

    @app.get("/api/v1/probe")
    async def probe():
        return {"ok": True}

    return TestClient(app), supabase


def test_shared_limiter_returns_429_and_retry_after(monkeypatch):
    client, supabase = _client_with_rpc(
        monkeypatch,
        rpc_result={"allowed": False, "retry_after_seconds": 7},
    )

    response = client.get("/api/v1/probe")

    assert response.status_code == 429
    assert response.json()["error"] == "rate_limit_exceeded"
    assert response.headers["Retry-After"] == "7"
    supabase.rpc.return_value.execute.assert_awaited_once()


def test_shared_limiter_fails_closed_with_503_when_rpc_fails(monkeypatch):
    client, supabase = _client_with_rpc(
        monkeypatch,
        rpc_error=RuntimeError("rpc unavailable"),
    )

    response = client.get("/api/v1/probe")

    assert response.status_code == 503
    assert response.json()["error"] == "rate_limiter_unavailable"
    assert response.headers["Retry-After"] == "1"
    supabase.rpc.return_value.execute.assert_awaited_once()


def test_shared_limiter_passes_request_when_rpc_allows(monkeypatch):
    client, supabase = _client_with_rpc(
        monkeypatch,
        rpc_result={"allowed": True, "retry_after_seconds": 0},
    )

    response = client.get("/api/v1/probe")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    supabase.rpc.return_value.execute.assert_awaited_once()


def test_options_bypasses_shared_limiter(monkeypatch):
    client, supabase = _client_with_rpc(
        monkeypatch,
        rpc_error=asyncio.TimeoutError(),
    )

    response = client.options("/api/v1/probe")

    assert response.status_code in {200, 405}
    supabase.rpc.assert_not_called()
