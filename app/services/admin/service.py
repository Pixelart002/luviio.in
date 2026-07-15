"""
Admin Service — Enterprise Business Logic
=========================================
Path: app/services/admin_service.py
"""
import time
from typing import Any, Dict
from app.repositories.admin_repo import AsyncAdminRepository
from app.core.exceptions import UnauthorizedAction
from app.enums.roles import UserRole
from app.utils.timestamp import ts_to_iso  # ✅ Imported our SSOT timestamp helper

class AdminService:
    def __init__(self):
        self.repo = AsyncAdminRepository()

    async def _assert_admin_access(self, user_id: str) -> Dict[str, Any]:
        """
        Internal helper: Fetches live profile and validates active admin status.
        Prevents repeating the same DB check across multiple methods.
        """
        profile = await self.repo.get_live_admin_profile(user_id)

        if not profile:
            raise UnauthorizedAction("No DB profile mapped to this UID")

        user_role = profile.get("role", "")
        is_active = profile.get("is_active", False)

        # Assuming UserRole is a str Enum (e.g. UserRole.ADMIN or UserRole.ADMIN.value)
        if user_role != UserRole.ADMIN and user_role != getattr(UserRole.ADMIN, "value", "admin") or not is_active:
            raise UnauthorizedAction(f"Non-admin or inactive access attempt ({user_role})")

        return profile

    async def verify_admin_access(self, user_id: str) -> Dict[str, Any]:
        """Business logic to verify if a user is an active admin."""
        profile = await self._assert_admin_access(user_id)

        safe_profile = {
            "id": profile.get("id"), 
            "email": profile.get("email"),
            "full_name": profile.get("full_name"), 
            "role": profile.get("role"),
            "is_active": profile.get("is_active"), 
            "created_at": ts_to_iso(profile.get("created_at")), # ✅ Safe ISO date
        }
        return {
            "verified": True, 
            "profile": safe_profile, 
            "timestamp": ts_to_iso(time.time())  # ✅ Converted to ISO-8601 string
        }

    async def get_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        """Business logic to fetch global admin dashboard metrics."""
        # ✅ Reused the helper instead of writing the check again
        await self._assert_admin_access(user_id)

        stats = await self.repo.get_dashboard_stats()
        return {
            "verified": True, 
            "stats": stats, 
            "timestamp": ts_to_iso(time.time())  # ✅ Converted to ISO-8601 string
        }