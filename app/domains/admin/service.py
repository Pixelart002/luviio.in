"""Admin domain service — enterprise business logic."""
import time
from typing import Any, Dict

from fastapi import HTTPException, status

from app.constants.admin_messages import AdminSecurityMessages
from app.domains.admin.repository import AsyncAdminRepository
from app.permissions.policies.admin_policies import AdminPolicy
from app.utils.timestamp import ts_to_iso


class AdminService:
    def __init__(self) -> None:
        self.repo = AsyncAdminRepository()

    async def verify_admin_access(self, user_id: str) -> Dict[str, Any]:
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        profile = AdminPolicy.assert_is_active_admin(raw_profile)
        return {"verified": True, "profile": {k: profile.get(k) for k in ("id", "email", "full_name", "role", "is_active", "created_at")}, "timestamp": ts_to_iso(time.time())}

    async def get_dashboard_metrics(self, user_id: str) -> Dict[str, Any]:
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        AdminPolicy.assert_is_active_admin(raw_profile)
        try:
            stats = await self.repo.get_dashboard_stats()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=AdminSecurityMessages.TELEMETRY_FAILED) from exc
        return {"verified": True, "stats": stats, "timestamp": ts_to_iso(time.time())}

    async def get_reports(self, user_id: str) -> Dict[str, Any]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        return await self.repo.get_report_summary()

    async def get_payments(self, user_id: str) -> list[dict[str, Any]]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        return await self.repo.get_payment_report()

    async def get_audit_logs(self, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        return await self.repo.get_audit_logs(limit)
