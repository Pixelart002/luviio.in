"""
Push Notifications Repository — Async Enterprise Grade
======================================================
Path: app/repositories/push_repo.py
"""
import logging
from typing import Any, Dict, List
from fastapi import HTTPException, status
from app.core.supabase import get_async_admin_supabase
from app.constants.push_messages import PushSecurityMessages

logger = logging.getLogger(__name__)

class AsyncPushRepository:
    def __init__(self) -> None:
        pass
    
    async def count_user_subscriptions(self, user_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("push_subscriptions").select("id", count="exact").eq("user_id", user_id).limit(1).execute()
            return res.count if res and hasattr(res, "count") and res.count is not None else 0
        except Exception as exc:
            logger.error("DB Error counting subscriptions for user %s: %s", user_id[:8], exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def get_stale_subscriptions(self, user_id: str, limit_count: int) -> List[str]:
        admin_sb = await get_async_admin_supabase()
        try:
            old = await admin_sb.table("push_subscriptions").select("id").eq("user_id", user_id).order("created_at", desc=False).limit(limit_count).execute()
            if old and hasattr(old, "data") and old.data:
                return [row["id"] for row in old.data]
            return []
        except Exception as exc:
            logger.error("DB Error fetching stale subscriptions for user %s: %s", user_id[:8], exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def delete_subscriptions(self, ids: List[str]) -> None:
        if not ids:
            return
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("push_subscriptions").delete().in_("id", ids).execute()
        except Exception as exc:
            logger.error("DB Error deleting subscriptions batch: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def is_duplicate_subscription(self, user_id: str, endpoint: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            existing = await admin_sb.table("push_subscriptions").select("id").eq("endpoint", endpoint).eq("user_id", user_id).limit(1).execute()
            return bool(existing and hasattr(existing, "data") and existing.data)
        except Exception as exc:
            logger.error("DB Error checking duplicate subscription for user %s: %s", user_id[:8], exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def upsert_subscription(self, user_id: str, endpoint: str, subscription_json: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("push_subscriptions").upsert(
                {"endpoint": endpoint, "user_id": user_id, "subscription_json": subscription_json},
                on_conflict="endpoint"
            ).execute()
        except Exception as exc:
            logger.error("DB Error upserting push subscription for user %s: %s", user_id[:8], exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def delete_subscription_by_endpoint(self, endpoint: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            result = await admin_sb.table("push_subscriptions").delete().eq("endpoint", endpoint).execute()
            return len(result.data) if result and hasattr(result, "data") and result.data else 0
        except Exception as exc:
            logger.error("DB Error deleting subscription by endpoint: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.DB_ERROR) from exc

    async def get_total_subscriptions_count(self) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("push_subscriptions").select("id", count="exact").limit(1).execute()
            return res.count if res and hasattr(res, "count") and res.count is not None else 0
        except Exception as exc:
            logger.error("DB Error fetching total subscriptions count: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.STATS_ERROR) from exc

    async def get_unique_subscribed_users(self) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("push_subscriptions").select("user_id").execute()
            return len(set(row["user_id"] for row in (getattr(res, "data", None) or [])))
        except Exception as exc:
            logger.error("DB Error fetching unique subscribed users: %s", exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=PushSecurityMessages.STATS_ERROR) from exc