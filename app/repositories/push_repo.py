"""
Push Notifications Repository — Async Enterprise Grade
======================================================
Path: app/repositories/push_repo.py
"""
import logging
from typing import Any, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPushRepository:
    def __init__(self):
        self.admin_sb = get_async_admin_supabase()
    
    async def count_user_subscriptions(self, user_id: str) -> int:
        try:
            res = await self.admin_sb.table("push_subscriptions").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
            return res.count if res and hasattr(res, "count") and res.count else 0
        except Exception as exc:
            logger.warning("Failed to count subscriptions for user %.8s: %s", user_id, exc)
            return 0

    async def get_stale_subscriptions(self, user_id: str, limit_count: int) -> List[str]:
        try:
            old = await self.admin_sb.table("push_subscriptions").select("id").eq("user_id", user_id).order("created_at", desc=False).limit(limit_count).execute()
            if old and hasattr(old, "data") and old.data:
                return [row["id"] for row in old.data]
        except Exception as exc:
            logger.warning("Failed to fetch stale subscriptions | user=%.8s: %s", user_id, exc)
        return []

    async def delete_subscriptions(self, ids: List[str]) -> None:
        if ids:
            await self.admin_sb.table("push_subscriptions").delete().in_("id", ids).execute()

    async def is_duplicate_subscription(self, user_id: str, endpoint: str) -> bool:
        try:
            existing = await self.admin_sb.table("push_subscriptions").select("id").eq("endpoint", endpoint).eq("user_id", user_id).limit(1).execute()
            return bool(existing and hasattr(existing, "data") and existing.data)
        except Exception:
            return False

    async def upsert_subscription(self, user_id: str, endpoint: str, subscription_json: str) -> None:
        await self.admin_sb.table("push_subscriptions").upsert(
            {"endpoint": endpoint, "user_id": user_id, "subscription_json": subscription_json},
            on_conflict="endpoint"
        ).execute()

    async def delete_subscription_by_endpoint(self, endpoint: str) -> int:
        result = await self.admin_sb.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
        return len(result.data) if result and hasattr(result, "data") and result.data else 0

    async def get_total_subscriptions_count(self) -> int:
        res = await self.admin_sb.table("push_subscriptions").select("id", count="exact").limit(1).execute()
        return res.count if res and hasattr(res, "count") and res.count else 0

    async def get_unique_subscribed_users(self) -> int:
        res = await self.admin_sb.table("push_subscriptions").select("user_id").execute()
        return len(set(row["user_id"] for row in (getattr(res, "data", None) or [])))