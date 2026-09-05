"""Manager-scoped settings service."""
from typing import Any, Dict
from fastapi import HTTPException, status

from app.domains.settings.core_engine import SettingsCoreEngine
from app.permissions.policies.settings_policies import SettingsPolicy
from app.enums.roles import UserRole
from app.enums.settings import SettingCategory


class ManagerSettingsService:
    """Restricted write access for store operations."""

    def __init__(self) -> None:
        self.engine = SettingsCoreEngine()

    async def update_operational_setting(
        self, key: str, new_value: Any, manager_id: str
    ) -> Dict[str, Any]:
        existing = await self.engine.fetch_by_key(key)
        allowed_categories = [
            SettingCategory.OPERATIONAL.value,
            SettingCategory.UI_UX.value,
        ]
        if existing.get("category") not in allowed_categories:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Managers cannot modify financial or core system settings.",
            )

        manager_role = UserRole.MANAGER.value if hasattr(UserRole.MANAGER, "value") else "manager"
        SettingsPolicy.assert_can_modify(existing, manager_role)
        SettingsPolicy.assert_valid_data_type(new_value, existing["data_type"])
        return await self.engine.mutate_setting(
            key=key,
            new_value=new_value,
            old_value=existing["value"],
            user_id=manager_id,
            reason="Manager Operational Update",
        )
