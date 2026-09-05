from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.asyncio
async def test_health_database_success(monkeypatch):
    from app.infrastructure.health import router as health

    query = Mock()
    query.select.return_value = query
    query.limit.return_value = query
    query.execute = AsyncMock(return_value=Mock(data=[]))
    supabase = Mock()
    supabase.table.return_value = query

    monkeypatch.setattr(health, "get_async_admin_supabase", AsyncMock(return_value=supabase))

    response = await health.health_check()

    assert response["data"]["status"] == "ok"
