"""Push Service — enterprise orchestration and concurrent dispatch."""
import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import HTTPException, status

from app.constants.push_messages import PushMessages, PushRules
from app.core.supabase import get_async_admin_supabase
from app.domains.notifications.repository import AsyncPushRepository
from app.integrations.push.webpush_impl import send_push_to_user
from app.permissions.policies.push_policies import VAPID_PUBLIC_KEY, PushPolicy

logger = logging.getLogger(__name__)


class PushService:
    def __init__(self):
        self.repo = AsyncPushRepository()

    def get_vapid_key(self) -> Dict[str, str]:
        return {"public_key": PushPolicy.assert_vapid_configured()}

    async def _cleanup_stale_subscriptions(self, user_id: str) -> int:
        count = await self.repo.count_user_subscriptions(user_id)
        if count >= PushRules.MAX_SUBSCRIPTIONS_PER_USER:
            stale_ids = await self.repo.get_stale_subscriptions(
                user_id,
                count - PushRules.MAX_SUBSCRIPTIONS_PER_USER + 1,
            )
            if stale_ids:
                await self.repo.delete_subscriptions(stale_ids)
                return len(stale_ids)
        return 0

    async def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> Dict[str, Any]:
        PushPolicy.assert_valid_endpoint(endpoint)
        if await self.repo.is_duplicate_subscription(user_id, endpoint):
            return {"message": "Already subscribed", "cleaned": 0}
        cleaned = await self._cleanup_stale_subscriptions(user_id)
        await self.repo.upsert_subscription(
            user_id,
            endpoint,
            json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}),
        )
        return {"message": PushMessages.SUBSCRIBED, "cleaned": cleaned}

    async def unsubscribe(self, endpoint: str) -> None:
        await self.repo.delete_subscription_by_endpoint(endpoint)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        count = await self.repo.count_user_subscriptions(user_id)
        return {
            "subscribed": count > 0,
            "subscription_count": count,
            "max_allowed": PushRules.MAX_SUBSCRIPTIONS_PER_USER,
            "vapid_configured": bool(VAPID_PUBLIC_KEY),
        }

    async def send_test_notification(self, user_id: str) -> Dict[str, Any]:
        count = await self.repo.count_user_subscriptions(user_id)
        if count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active subscriptions found for this account — subscribe on this device first.",
            )
        sent = await send_push_to_user(
            user_id=user_id,
            title="Luviio — Test Notification",
            body="If you're seeing this, push notifications are working end-to-end.",
            icon="/icon-192.png",
            url="/",
        )
        return {"sent": sent, "subscriptions_targeted": count}

    async def _resolve_audience(self, user_ids: List[str] | None) -> List[str]:
        if user_ids is not None:
            return user_ids
        sb = await get_async_admin_supabase()
        result = await sb.table("push_subscriptions").select("user_id").execute()
        return sorted({str(row["user_id"]) for row in (getattr(result, "data", None) or []) if row.get("user_id")})

    async def send_batch_notification(
        self,
        user_ids: List[str] | None,
        title: str,
        body: str,
        icon: str,
        url: str,
    ) -> Dict[str, Any]:
        audience = await self._resolve_audience(user_ids)
        PushPolicy.assert_valid_batch_size(audience)
        results: Dict[str, Any] = {"success": 0, "failed": 0, "audience": len(audience), "details": []}
        semaphore = asyncio.Semaphore(20)

        async def bounded_send(uid: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    sent = await send_push_to_user(user_id=uid, title=title, body=body, icon=icon, url=url)
                    return {"user_id": uid, "status": "sent" if sent > 0 else "no_subscription", "success": sent > 0}
                except Exception as exc:
                    logger.warning("Push dispatch failed for user %s: %s", uid[:8], str(exc)[:100])
                    return {"user_id": uid, "status": "error", "success": False}

        outcomes = await asyncio.gather(*(bounded_send(uid) for uid in audience), return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, Exception):
                results["failed"] += 1
                continue
            results["success" if outcome["success"] else "failed"] += 1
            results["details"].append({"user_id": outcome["user_id"], "status": outcome["status"]})
        return results

    async def get_stats(self) -> Dict[str, Any]:
        total = await self.repo.get_total_subscriptions_count()
        unique_users = await self.repo.get_unique_subscribed_users()
        return {
            "total_subscriptions": total,
            "unique_users": unique_users,
            "avg_per_user": round(total / unique_users, 1) if unique_users > 0 else 0,
            "vapid_configured": bool(VAPID_PUBLIC_KEY),
        }
