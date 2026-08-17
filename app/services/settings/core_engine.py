import time
import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status

from app.repositories.settings_repo import AsyncSettingsRepository
from app.events.bus import get_event_bus
from app.events.settings_events import SettingUpdatedEvent, SettingResetEvent
from app.constants.settings_messages import SettingsRules, SettingsSecurityMessages

logger = logging.getLogger(__name__)

# Enterprise Singleton Cache-Aside State
_settings_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0.0

class SettingsCoreEngine:
    """Core Engine handling ONLY Cache, DB reads/writes, and Event Dispatching."""
    
    def __init__(self):
        self.repo = AsyncSettingsRepository()

    def is_cache_valid(self) -> bool:
        return (time.time() - _cache_timestamp) < SettingsRules.CACHE_TTL_SECONDS and bool(_settings_cache)

    def invalidate_cache(self) -> None:
        global _settings_cache, _cache_timestamp
        _settings_cache.clear()
        _cache_timestamp = 0.0
        logger.info("System Settings in-memory cache invalidated.")

    async def fetch_all(self, category: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        global _settings_cache, _cache_timestamp
        
        # Safe Cache Return
        if not force_refresh and not category and self.is_cache_valid():
            return list(_settings_cache.values())

        items = await self.repo.get_all_settings(category)
        
        # Populate Cache only if fetching everything
        if not category:
            _settings_cache = {item["key"]: item for item in items}
            _cache_timestamp = time.time()
            
        return items

    async def fetch_by_key(self, key: str) -> Dict[str, Any]:
        # Cache Warming
        if not self.is_cache_valid() or key not in _settings_cache:
            await self.fetch_all() 
            
        if key in _settings_cache:
            return _settings_cache[key]
            
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=SettingsSecurityMessages.NOT_FOUND
        )

    async def mutate_setting(self, key: str, new_value: Any, old_value: Any, user_id: str, reason: str) -> Dict[str, Any]:
        updated = await self.repo.update_setting_value(key, new_value)
        self.invalidate_cache()
        
        try:
            get_event_bus().publish(SettingUpdatedEvent(
                key=key, old_value=old_value, new_value=new_value, updated_by=user_id, reason=reason
            ))
        except Exception as e:
            logger.error("Failed to dispatch SettingUpdatedEvent: %s", e)
            
        return updated

    async def reset_to_default(self, key: str, default_value: Any, user_id: str) -> Dict[str, Any]:
        restored = await self.repo.reset_setting_to_default(key, default_value)
        self.invalidate_cache()
        
        try:
            get_event_bus().publish(SettingResetEvent(
                key=key, restored_value=default_value, reset_by=user_id
            ))
        except Exception as e:
            logger.error("Failed to dispatch SettingResetEvent: %s", e)
            
        return restored