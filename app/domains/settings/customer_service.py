"""Customer/public settings service."""
from typing import Any, Dict, List
from fastapi import HTTPException, status

from app.domains.settings.core_engine import SettingsCoreEngine
from app.constants.settings_messages import SettingsSecurityMessages


class CustomerSettingsService:
    """Strictly read-only service for guests and customers."""

    def __init__(self) -> None:
        self.engine = SettingsCoreEngine()

    async def get_store_config(self) -> List[Dict[str, Any]]:
        all_settings = await self.engine.fetch_all()
        return [setting for setting in all_settings if setting.get("is_public") is True]

    async def get_setting(self, key: str) -> Dict[str, Any]:
        setting = await self.engine.fetch_by_key(key)
        if not setting.get("is_public", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=SettingsSecurityMessages.NOT_FOUND,
            )
        return setting
