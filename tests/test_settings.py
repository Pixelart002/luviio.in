from unittest.mock import AsyncMock, Mock

import pytest


def test_settings_facade_uses_canonical_engine(monkeypatch):
    from app.services.settings.service import SettingsService

    engine = Mock()
    monkeypatch.setattr("app.services.settings.service.SettingsCoreEngine", lambda: engine)

    service = SettingsService()

    assert service.engine is engine


@pytest.mark.asyncio
async def test_maintenance_cache_is_fail_open(monkeypatch):
    from app.core.maintenance import maintenance_enabled

    monkeypatch.setattr(
        "app.core.maintenance.get_async_admin_supabase",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )

    assert await maintenance_enabled() is False
