"""Admin domain service — enterprise business logic."""
# ruff: noqa: I001 - keep imports aligned with the existing domain-module convention.
import asyncio
import copy
import time
from typing import Any, Dict

from cachetools import TTLCache
from fastapi import HTTPException, status

from app.constants.admin_messages import AdminSecurityMessages
from app.domains.admin.repository import AsyncAdminRepository
from app.permissions.policies.admin_policies import AdminPolicy
from app.permissions.policies.push_policies import VAPID_PUBLIC_KEY
from app.utils.timestamp import ts_to_iso


# A very short process-local cache avoids repeating the relatively expensive
# aggregate RPC on rapid dashboard refreshes. Authorization/profile validation
# still runs on every request; cached data contains no user-specific fields.
_DASHBOARD_SNAPSHOT_CACHE: TTLCache = TTLCache(maxsize=256, ttl=3)
_DASHBOARD_SNAPSHOT_LOCK = asyncio.Lock()


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

    async def get_dashboard_snapshot(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Return dashboard sections and real daily chart points in one cached snapshot."""
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        AdminPolicy.assert_is_active_admin(raw_profile)
        normalized_days = max(7, min(int(days), 90))
        # Layout preferences are user-specific, so the cache key must include
        # the verified administrator ID to prevent cross-account preference leaks.
        cache_key = (str(user_id), normalized_days)
        cached = _DASHBOARD_SNAPSHOT_CACHE.get(cache_key)
        if cached is not None:
            return copy.deepcopy(cached)

        async with _DASHBOARD_SNAPSHOT_LOCK:
            cached = _DASHBOARD_SNAPSHOT_CACHE.get(cache_key)
            if cached is not None:
                return copy.deepcopy(cached)
            try:
                snapshot = await self.repo.get_dashboard_snapshot(normalized_days, str(user_id))
            except Exception as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=AdminSecurityMessages.TELEMETRY_FAILED,
                ) from exc

            notifications = snapshot.setdefault("notifications", {})
            notifications["vapid_configured"] = bool(VAPID_PUBLIC_KEY)
            snapshot["admin_user_id"] = str(user_id)
            snapshot["verified"] = True
            snapshot["timestamp"] = ts_to_iso(time.time())
            _DASHBOARD_SNAPSHOT_CACHE[cache_key] = copy.deepcopy(snapshot)
            return snapshot

    async def save_dashboard_layout(self, user_id: str, layout: Dict[str, Any]) -> Dict[str, Any]:
        """Save a validated user layout and invalidate potentially stale snapshots."""
        raw_profile = await self.repo.get_live_admin_profile(user_id)
        AdminPolicy.assert_is_active_admin(raw_profile)
        try:
            result = await self.repo.save_dashboard_layout(user_id, layout)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to save dashboard preferences.",
            ) from exc
        # Saved layout belongs to one admin; clearing this tiny cache also avoids
        # returning a pre-update copy during the next dashboard navigation.
        _DASHBOARD_SNAPSHOT_CACHE.clear()
        return result

    async def get_reports(self, user_id: str) -> Dict[str, Any]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        return await self.repo.get_report_summary()

    async def get_payments(self, user_id: str, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        return await self.repo.get_payment_report(limit=limit, offset=offset)

    async def get_audit_logs(self, user_id: str, limit: int = 200) -> list[dict[str, Any]]:
        AdminPolicy.assert_is_active_admin(await self.repo.get_live_admin_profile(user_id))
        limit = max(1, min(int(limit), 500))
        return await self.repo.get_audit_logs(limit)
