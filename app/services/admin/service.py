"""
Admin Service — Enterprise Business Logic
=========================================
Path: app/services/admin/service.py
"""
import time
from typing import Any, Dict
from fastapi import HTTPException, status
from app.repositories.admin_repo import AsyncAdminRepository
from app.permissions.policies.admin_policies import AdminPolicy
from app.utils.timestamp import ts_to_iso
from app.constants.admin_messages import AdminSecurityMessages

class AdminService:
    def __init__(self) -> None:
        self.repo = AsyncAdminRepository()

    async def verify_admin_access(self, user_id: str) -> Dict[str, Any]:
        """Business logic to verify if a user is an active admin."""
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        profile = AdminPolicy.assert_is_active_admin(raw_profile)

        safe_profile = {
            "id": profile.get("id"), 
            "email": profile.get("email"),
            "full_name": profile.get("full_name"), 
            "role": profile.get("role"),
            "is_active": profile.get("is_active"), 
            "created_at": profile.get("created_at"),
        }
        return {
            "verified": True, 
            "profile": safe_profile, 
            "timestamp": ts_to_iso(time.time())
        }

    async def get_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        """Business logic to fetch global admin dashboard metrics."""
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        AdminPolicy.assert_is_active_admin(raw_profile)

        try:
            stats = await self.repo.get_dashboard_stats()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=AdminSecurityMessages.TELEMETRY_FAILED
            ) from exc

        return {
            "verified": True, 
            "stats": stats, 
            "timestamp": ts_to_iso(time.time())
        }