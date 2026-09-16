"""
Subscription Domain — Repository
=================================
Path: app/domains/subscriptions/repository.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class AsyncSubscriptionRepository:
    async def list_plans(self, active_only: bool = True) -> List[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            q = sb.table("subscription_plans").select("*").order("price_inr")
            if active_only:
                q = q.eq("is_active", True)
            res = await q.execute()
            return res.data or []
        except Exception as exc:
            logger.error("[REPO:SUB] list_plans failed: %s", exc)
            return []

    async def get_plan(self, plan_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("subscription_plans").select("*").eq("id", plan_id).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] get_plan failed: %s", exc)
            return None

    async def create_plan(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("subscription_plans").insert(data).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] create_plan failed: %s", exc)
            return None

    async def update_plan(self, plan_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("subscription_plans").update(data).eq("id", plan_id).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] update_plan failed: %s", exc)
            return None

    async def get_active_for_user(self, user_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            now = datetime.now(timezone.utc).isoformat()
            res = await (
                sb.table("user_subscriptions").select("*")
                .eq("user_id", user_id).eq("status", "active")
                .gt("ends_at", now)
                .order("ends_at", desc=True).limit(1).maybe_single().execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] get_active_for_user failed: %s", exc)
            return None

    async def get_latest_for_user(self, user_id: str) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_subscriptions").select("*")
                .eq("user_id", user_id)
                .order("starts_at", desc=True).limit(1).maybe_single().execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] get_latest_for_user failed: %s", exc)
            return None

    async def cancel_subscription(self, subscription_id: str, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await (
                sb.table("user_subscriptions").update(data)
                .eq("id", subscription_id).eq("status", "active")
                .maybe_single().execute()
            )
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] cancel failed: %s", exc)
            return None

    async def upsert_subscription(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        try:
            res = await sb.table("user_subscriptions").insert(data).maybe_single().execute()
            return res.data if res else None
        except Exception as exc:
            logger.error("[REPO:SUB] upsert failed: %s", exc)
            return None
