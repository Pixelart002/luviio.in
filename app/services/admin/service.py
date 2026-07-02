import time
from typing import Any, Dict
from app.repositories.admin_repo import AsyncAdminRepository
from app.core.exceptions import UnauthorizedAction
from app.enums.roles import UserRole

class AdminService:
    def __init__(self):
        self.repo = AsyncAdminRepository()

    async def verify_admin_access(self, user_id: str) -> Dict[str, Any]:
        """Business logic to verify if a user is an active admin."""
        profile = await self.repo.get_live_admin_profile(user_id)

        if not profile:
            raise UnauthorizedAction("No DB profile mapped to this UID")

        user_role = profile.get("role", "")
        is_active = profile.get("is_active", False)

        if user_role != UserRole.ADMIN or not is_active:
            raise UnauthorizedAction(f"Non-admin or inactive access attempt ({user_role})")

        safe_profile = {
            "id": profile.get("id"), 
            "email": profile.get("email"),
            "full_name": profile.get("full_name"), 
            "role": profile.get("role"),
            "is_active": profile.get("is_active"), 
            "created_at": profile.get("created_at"),
        }
        return {"verified": True, "profile": safe_profile, "timestamp": int(time.time())}

    async def get_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        """Business logic to fetch global admin dashboard metrics."""
        profile = await self.repo.get_live_admin_profile(user_id)
        if not profile or profile.get("role") != UserRole.ADMIN or not profile.get("is_active"):
            raise UnauthorizedAction("Access denied for telemetry aggregation")

        stats = await self.repo.get_dashboard_stats()
        return {"verified": True, "stats": stats, "timestamp": int(time.time())}