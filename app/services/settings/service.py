"""Backward-compatible facade for the canonical settings engine.

New code should use the role-specific services in this package. This facade
keeps the historical import path working while ensuring reads and writes use
one cache, repository, and event pipeline.
"""
from typing import Any, Dict, List, Optional

from app.services.settings.core_engine import SettingsCoreEngine
from app.permissions.policies.settings_policies import SettingsPolicy
from app.constants.settings_messages import SettingsSecurityMessages


class SettingsService:
    """Compatibility API delegating all storage work to ``SettingsCoreEngine``."""

    def __init__(self) -> None:
        self.engine = SettingsCoreEngine()

    async def get_all(
        self, category: Optional[str] = None, force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        return await self.engine.fetch_all(category=category, force_refresh=force_refresh)

    async def get_by_key(self, key: str) -> Dict[str, Any]:
        return await self.engine.fetch_by_key(key)

    async def update(
        self,
        key: str,
        new_value: Any,
        user_id: str,
        user_role: str,
        reason: str = "Admin override",
    ) -> Dict[str, Any]:
        existing = await self.engine.fetch_by_key(key)
        SettingsPolicy.assert_can_modify(existing, user_role)
        SettingsPolicy.assert_valid_data_type(new_value, existing["data_type"])
        return await self.engine.mutate_setting(
            key=key,
            new_value=new_value,
            old_value=existing["value"],
            user_id=user_id,
            reason=reason,
        )

    async def reset(self, key: str, user_id: str, user_role: str) -> Dict[str, Any]:
        existing = await self.engine.fetch_by_key(key)
        SettingsPolicy.assert_can_modify(existing, user_role)
        return await self.engine.reset_to_default(
            key=key,
            default_value=existing["default_value"],
            user_id=user_id,
        )
