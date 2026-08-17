from typing import Any, Dict, List, Optional
from app.services.settings.core_engine import SettingsCoreEngine
from app.permissions.policies.settings_policies import SettingsPolicy

class AdminSettingsService:
    """Full God-Mode Access for Financial & Security Settings."""
    
    def __init__(self):
        self.engine = SettingsCoreEngine()

    async def get_all(self, category: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Admins can view everything without filters."""
        return await self.engine.fetch_all(category=category, force_refresh=force_refresh)

    async def update_core_setting(self, key: str, new_value: Any, admin_id: str, role: str, reason: str) -> Dict[str, Any]:
        existing = await self.engine.fetch_by_key(key)
        
        # Full ABAC Guard
        SettingsPolicy.assert_can_modify(existing, role)
        SettingsPolicy.assert_valid_data_type(new_value, existing["data_type"])

        return await self.engine.mutate_setting(
            key=key, 
            new_value=new_value, 
            old_value=existing["value"], 
            user_id=admin_id, 
            reason=reason
        )

    async def reset_to_default(self, key: str, admin_id: str, role: str) -> Dict[str, Any]:
        existing = await self.engine.fetch_by_key(key)
        
        # ABAC Guard
        SettingsPolicy.assert_can_modify(existing, role)

        return await self.engine.reset_to_default(
            key=key,
            default_value=existing["default_value"],
            user_id=admin_id
        )