import json
import logging
import os
from typing import Any, Dict, List
from starlette.concurrency import run_in_threadpool

from app.core.supabase import get_admin_supabase
from app.repositories.push_repo import AsyncPushRepository
from app.integrations.push.webpush_impl import send_push_to_user
from app.core.exceptions import LuviioException

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
MAX_SUBSCRIPTIONS_PER_USER = 5

class PushService:
    def __init__(self):
        self.repo = AsyncPushRepository()

    def get_vapid_key(self) -> Dict[str, str]:
        if not VAPID_PUBLIC_KEY:
            raise LuviioException("Push notifications not configured", "NOT_CONFIGURED", 503)
        return {"public_key": VAPID_PUBLIC_KEY}

    async def _cleanup_stale_subscriptions(self, user_id: str) -> int:
        count = await self.repo.count_user_subscriptions(user_id)
        if count >= MAX_SUBSCRIPTIONS_PER_USER:
            to_remove = count - MAX_SUBSCRIPTIONS_PER_USER + 1
            stale_ids = await self.repo.get_stale_subscriptions(user_id, to_remove)
            if stale_ids:
                await self.repo.delete_subscriptions(stale_ids)
                return len(stale_ids)
        return 0

    async def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> Dict[str, Any]:
        if await self.repo.is_duplicate_subscription(user_id, endpoint):
            return {"message": "Already subscribed", "cleaned": 0}

        cleaned = await self._cleanup_stale_subscriptions(user_id)

        if not endpoint.startswith("https://"):
            raise LuviioException("Invalid push endpoint — must be HTTPS", "INVALID_ENDPOINT", 400)

        sub_json = json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}})

        try:
            await self.repo.upsert_subscription(user_id, endpoint, sub_json)
        except Exception as e:
            logger.error(f"Push subscription save failed: {e}")
            raise LuviioException("Failed to subscribe to push notifications", "DB_ERROR", 500)

        return {"message": "Subscribed successfully", "cleaned": cleaned}

    async def unsubscribe(self, endpoint: str) -> None:
        try:
            await self.repo.delete_subscription_by_endpoint(endpoint)
        except Exception as e:
            logger.error(f"Unsubscribe failed: {e}")
            raise LuviioException("Failed to unsubscribe", "DB_ERROR", 500)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        count = await self.repo.count_user_subscriptions(user_id)
        return {
            "subscribed": count > 0, 
            "subscription_count": count, 
            "max_allowed": MAX_SUBSCRIPTIONS_PER_USER, 
            "vapid_configured": bool(VAPID_PUBLIC_KEY)
        }

    async def send_batch_notification(self, user_ids: List[str], title: str, body: str, icon: str, url: str) -> Dict[str, Any]:
        sb = get_admin_supabase()
        results = {"success": 0, "failed": 0, "details": []}
        
        for user_id in user_ids:
            try:
                sent = await run_in_threadpool(send_push_to_user, sb_admin=sb, user_id=user_id, title=title, body=body, icon=icon, url=url)
                if sent > 0:
                    results["success"] += 1
                    results["details"].append({"user_id": user_id, "status": "sent"})
                else:
                    results["failed"] += 1
                    results["details"].append({"user_id": user_id, "status": "no_subscription"})
            except Exception as exc:
                results["failed"] += 1
                results["details"].append({"user_id": user_id, "status": f"error: {str(exc)[:100]}"})
        
        return results

    async def get_stats(self) -> Dict[str, Any]:
        try:
            total = await self.repo.get_total_subscriptions_count()
            unique_users = await self.repo.get_unique_subscribed_users()
            return {
                "total_subscriptions": total, 
                "unique_users": unique_users,
                "avg_per_user": round(total / unique_users, 1) if unique_users > 0 else 0,
                "vapid_configured": bool(VAPID_PUBLIC_KEY),
            }
        except Exception:
            raise LuviioException("Failed to fetch push notification statistics", "DB_ERROR", 500)