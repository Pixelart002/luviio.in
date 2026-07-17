"""
Admin Service — Enterprise Business Logic
=========================================
Path: app/services/admin_service.py
"""
import time
from typing import Any, Dict
from app.repositories.admin_repo import AsyncAdminRepository
from app.permissions.policies.admin_policies import AdminPolicy
from app.utils.timestamp import ts_to_iso

class AdminService:
    def __init__(self):
        self.repo = AsyncAdminRepository()

    async def verify_admin_access(self, user_id: str) -> Dict[str, Any]:
        """
        Business logic to verify active admin status.
        Applies ABAC policies against live DB state.
        """
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        
        # 🛡️ Enforce ABAC Policy (Will raise 403 if invalid or deactivated)
        profile = AdminPolicy.assert_can_access_portal(raw_profile)

        safe_profile = {
            "id": profile.get("id"), 
            "email": profile.get("email"),
            "full_name": profile.get("full_name"), 
            "role": profile.get("role"),
            "is_active": profile.get("is_active"), 
            "created_at": ts_to_iso(profile.get("created_at")),
        }
        
        return {
            "verified": True, 
            "profile": safe_profile, 
            "timestamp": ts_to_iso(time.time())
        }

    async def get_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        """Fetch global telemetry after asserting ABAC security compliance."""
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        
        # 🛡️ Enforce ABAC Policy
        AdminPolicy.assert_can_access_portal(raw_profile)

        stats = await self.repo.get_dashboard_stats()
        return {
            "verified": True, 
            "stats": stats, 
            "timestamp": ts_to_iso(time.time())
        }