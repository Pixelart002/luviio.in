from unittest.mock import AsyncMock, patch

import pytest

from app.domains.settings.core_engine import SettingsCoreEngine


@pytest.mark.asyncio
async def test_identical_setting_update_is_a_noop() -> None:
    engine = SettingsCoreEngine()
    existing = {"key": "maintenance_mode", "value": False}
    engine.repo.update_setting_value = AsyncMock()
    engine.fetch_by_key = AsyncMock(return_value=existing)

    with patch("app.domains.settings.core_engine.get_event_bus") as event_bus:
        result = await engine.mutate_setting(
            key="maintenance_mode",
            new_value=False,
            old_value=False,
            user_id="test-user",
            reason="test",
        )

    assert result is existing
    engine.repo.update_setting_value.assert_not_awaited()
    event_bus.return_value.publish.assert_not_called()


@pytest.mark.asyncio
async def test_changed_setting_persists_and_emits_event() -> None:
    engine = SettingsCoreEngine()
    updated = {"key": "maintenance_mode", "value": True}
    engine.repo.update_setting_value = AsyncMock(return_value=updated)

    with patch("app.domains.settings.core_engine.get_event_bus") as event_bus:
        result = await engine.mutate_setting(
            key="maintenance_mode",
            new_value=True,
            old_value=False,
            user_id="test-user",
            reason="test",
        )

    assert result == updated
    engine.repo.update_setting_value.assert_awaited_once_with("maintenance_mode", True)
    event_bus.return_value.publish.assert_called_once()


@pytest.mark.asyncio
async def test_reset_to_existing_default_is_a_noop() -> None:
    engine = SettingsCoreEngine()
    existing = {"key": "maintenance_mode", "value": False}
    engine.fetch_by_key = AsyncMock(return_value=existing)
    engine.repo.reset_setting_to_default = AsyncMock()

    with patch("app.domains.settings.core_engine.get_event_bus") as event_bus:
        result = await engine.reset_to_default(
            key="maintenance_mode",
            default_value=False,
            user_id="test-user",
        )

    assert result is existing
    engine.repo.reset_setting_to_default.assert_not_awaited()
    event_bus.return_value.publish.assert_not_called()
