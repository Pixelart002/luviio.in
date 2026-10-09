from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cron.tasks import rate_limit_tasks


@pytest.mark.asyncio
async def test_cleanup_http_token_bucket_state_calls_service_role_rpc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = MagicMock()
    supabase.rpc.return_value.execute = AsyncMock(
        return_value=SimpleNamespace(data=3)
    )
    monkeypatch.setattr(
        rate_limit_tasks,
        "get_async_admin_supabase",
        AsyncMock(return_value=supabase),
    )

    task = getattr(rate_limit_tasks.cleanup_http_token_bucket_state_job, "__wrapped__")
    await task()

    supabase.rpc.assert_called_once_with("cleanup_http_token_bucket_state", {})
    supabase.rpc.return_value.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_http_token_bucket_state_handles_rpc_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    supabase = MagicMock()
    supabase.rpc.return_value.execute = AsyncMock(side_effect=RuntimeError("rpc unavailable"))
    monkeypatch.setattr(
        rate_limit_tasks,
        "get_async_admin_supabase",
        AsyncMock(return_value=supabase),
    )

    task = getattr(rate_limit_tasks.cleanup_http_token_bucket_state_job, "__wrapped__")
    await task()

    supabase.rpc.assert_called_once_with("cleanup_http_token_bucket_state", {})
    supabase.rpc.return_value.execute.assert_awaited_once()
