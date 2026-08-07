"""
Settings Service — Enterprise Orchestration & Cache-Aside
=========================================================
Path: app/services/settings/service.py
"""
import time
import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from app.repositories.settings_repo import AsyncSettingsRepository
from app.permissions.policies.settings_policies import SettingsPolicy
from app.constants.settings_messages import SettingsRules
from app.events.bus import get_event_bus
from app.events.settings_events import SettingUpdatedEvent, SettingResetEvent
from app.constants.settings_messages import SettingsSecurityMessages

logger = logging.getLogger(__name__)

# In-Memory Cache-Aside State
_settings_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0.0

class SettingsService:
    def __init__(self):
        self.repo = AsyncSettingsRepository()

    def _is_cache_valid(self) -> bool:
        return (time.time() - _cache_timestamp) < SettingsRules.CACHE_TTL_SECONDS and bool(_settings_cache)

    def _invalidate_cache(self) -> None:
        global _settings_cache, _cache_timestamp
        _settings_cache.clear()
        _cache_timestamp = 0.0
        logger.info("System Settings in-memory cache invalidated.")

    async def get_all(self, category: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        global _settings_cache, _cache_timestamp
        if not force_refresh and not category and self._is_cache_valid():
            return list(_settings_cache.values())

        items = await self.repo.get_all_settings(category)
        if not category:
            _settings_cache = {item["key"]: item for item in items}
            _cache_timestamp = time.time()
        return items

    # 🔥 FIX APPLIED HERE: Cache Warming & Safe Reading
    async def get_by_key(self, key: str) -> Dict[str, Any]:
        # 1. Agar cache expire ho gaya ya khaali hai, toh "Warm Up" karo!
        if not self._is_cache_valid() or key not in _settings_cache:
            await self.get_all() # Ye DB se saari settings layega aur cache bhar dega
            
        # 2. Ab cache me se uthao (0ms delay)
        if key in _settings_cache:
            return _settings_cache[key]
            
        # 3. Agar aisi setting hai hi nahi (Typo in key)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=SettingsSecurityMessages.NOT_FOUND
        )

    async def update(self, key: str, new_value: Any, user_id: str, user_role: str, reason: str = "Admin override") -> Dict[str, Any]:
        existing = await self.repo.get_setting_by_key(key)
        if not existing:
             raise HTTPException(status_code=404, detail=SettingsSecurityMessages.NOT_FOUND)
        
        # 🛡️ Step 1: ABAC Lock & Role Check
        SettingsPolicy.assert_can_modify(existing, user_role)
        # 🛡️ Step 2: Strict Data Type Compliance
        SettingsPolicy.assert_valid_data_type(new_value, existing["data_type"])

        old_value = existing["value"]
        updated = await self.repo.update_setting_value(key, new_value)
        
        # 🔄 Step 3: Invalidate Cache
        self._invalidate_cache()

        # 📢 Step 4: Dispatch Event
        try:
            get_event_bus().publish(SettingUpdatedEvent(
                key=key, old_value=old_value, new_value=new_value, updated_by=user_id, reason=reason
            ))
        except Exception as e:
            logger.error("Failed to dispatch SettingUpdatedEvent: %s", e)

        return updated

    async def reset(self, key: str, user_id: str, user_role: str) -> Dict[str, Any]:
        existing = await self.repo.get_setting_by_key(key)
        if not existing:
             raise HTTPException(status_code=404, detail=SettingsSecurityMessages.NOT_FOUND)
             
        SettingsPolicy.assert_can_modify(existing, user_role)

        default_value = existing["default_value"]
        restored = await self.repo.reset_setting_to_default(key, default_value)
        
        self._invalidate_cache()

        try:
            get_event_bus().publish(SettingResetEvent(
                key=key, restored_value=default_value, reset_by=user_id
            ))
        except Exception as e:
            logger.error("Failed to dispatch SettingResetEvent: %s", e)

        return restored