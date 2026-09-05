"""
Settings Repository — Async Enterprise Grade
============================================
Path: app/repositories/settings_repo.py
"""
import logging
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from app.core.supabase import get_async_admin_supabase
from app.constants.settings_messages import SettingsSecurityMessages

logger = logging.getLogger(__name__)

class AsyncSettingsRepository:
    def __init__(self):
        pass

    async def get_all_settings(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            q = admin_sb.table("system_settings").select("*").order("category").order("key")
            if category:
                q = q.eq("category", category)
            res = await q.execute()
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error fetching settings: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=SettingsSecurityMessages.DB_OPERATION_FAILED) from exc

    async def get_setting_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("system_settings").select("*").eq("key", key).limit(1).execute()
            data = getattr(res, "data", None)
            return data[0] if data and len(data) > 0 else None
        except Exception as exc:
            logger.error("DB Error fetching setting key '%s': %s", key, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=SettingsSecurityMessages.DB_OPERATION_FAILED) from exc

    async def update_setting_value(self, key: str, new_value: Any) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("system_settings").update({"value": new_value}).eq("key", key).select("*").execute()
            data = getattr(res, "data", None)
            if data and len(data) > 0:
                return data[0]
            raise RuntimeError("Update succeeded but returned empty payload.")
        except Exception as exc:
            logger.error("DB Error updating setting '%s': %s", key, exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=SettingsSecurityMessages.DB_OPERATION_FAILED) from exc

    async def reset_setting_to_default(self, key: str, default_value: Any) -> Dict[str, Any]:
        return await self.update_setting_value(key, default_value)