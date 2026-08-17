from typing import Any, Dict, List
from fastapi import HTTPException, status

from app.services.settings.core_engine import SettingsCoreEngine
from app.constants.settings_messages import SettingsSecurityMessages

class CustomerSettingsService:
    """Strictly READ-ONLY service for Guests and Customers. 100% Secure."""
    
    def __init__(self):
        self.engine = SettingsCoreEngine()

    async def get_store_config(self) -> List[Dict[str, Any]]:
        """Fetch only public store configurations safely."""
        all_settings = await self.engine.fetch_all()
        # Strictly return only settings flagged as public
        return [s for s in all_settings if s.get("is_public") is True]

    async def get_setting(self, key: str) -> Dict[str, Any]:
        """Fetch a specific public setting."""
        setting = await self.engine.fetch_by_key(key)
        
        # Silent 404 block for non-public keys to prevent enumeration hacking
        if not setting.get("is_public", False):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=SettingsSecurityMessages.NOT_FOUND
            )
            
        return setting