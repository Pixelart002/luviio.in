"""
Push Notifications Repository — Async Enterprise Grade
======================================================
Path: app/repositories/push_repo.py
"""
import logging
from typing import Any, List, Dict
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPushRepository:
    """Stateless execution preventing coroutine state crashes and thread locks."""
    
    async def count_user_subscriptions(self, user_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("push_subscriptions").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
            return res.count if res and getattr(res, "count", None) else 0
        except Exception as exc:
            logger.warning("Failed to count subscriptions for user %s: %s", user_id[:8], exc)
            return 0

    async def get_stale_subscriptions(self, user_id: str, limit_count: int) -> List[str]:
        admin_sb = await get_async_admin_supabase()
        try:
            old = await admin_sb.table("push_subscriptions").select("id").eq("user_id", user_id).order("created_at", desc=False).limit(limit_count).execute()
            if old and getattr(old, "data", None):
                return [row["id"] for row in old.data]
        except Exception as exc:
            logger.warning("Failed to fetch stale subscriptions for %s: %s", user_id[:8], exc)
        return []

    async def delete_subscriptions(self, ids: List[str]) -> None:
        if not ids: return
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("push_subscriptions").delete().in_("id", ids).execute()

    async def is_duplicate_subscription(self, user_id: str, endpoint: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            existing = await admin_sb.table("push_subscriptions").select("id").eq("endpoint", endpoint).eq("user_id", user_id).limit(1).execute()
            return bool(getattr(existing, "data", None))
        except Exception:
            return False

    async def upsert_subscription(self, user_id: str, endpoint: str, subscription_json: str) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("push_subscriptions").upsert(
            {"endpoint": endpoint, "user_id": user_id, "subscription_json": subscription_json},
            on_conflict="endpoint"
        ).execute()

    async def delete_subscription_by_endpoint(self, endpoint: str) -> int:
        admin_sb = await get_async_admin_supabase()
        result = await admin_sb.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
        return len(result.data) if result and getattr(result, "data", None) else 0

    async def get_endpoints_for_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        if not user_ids: return []
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("push_subscriptions").select("user_id, endpoint, subscription_json").in_("user_id", user_ids).execute()
        return getattr(res, "data", None) or []

    async def get_total_subscriptions_count(self) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("push_subscriptions").select("id", count="exact").limit(1).execute()
        return res.count if res and getattr(res, "count", None) else 0

    async def get_unique_subscribed_users(self) -> int:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("push_subscriptions").select("user_id").execute()
        return len(set(row["user_id"] for row in (getattr(res, "data", None) or [])))