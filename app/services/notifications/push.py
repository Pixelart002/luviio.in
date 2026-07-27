"""
Push Service — Enterprise Orchestration & Concurrent Dispatch
=============================================================
Path: app/services/notifications/push.py
"""
import json
import asyncio
import logging
from typing import Any, Dict, List
from fastapi import HTTPException, status

from app.repositories.push_repo import AsyncPushRepository
from app.integrations.push.webpush_impl import send_push_to_user
from app.permissions.policies.push_policies import PushPolicy, VAPID_PUBLIC_KEY
from app.constants.push_messages import PushMessages, PushSecurityMessages, PushRules

logger = logging.getLogger(__name__)

class PushService:
    def __init__(self) -> None:
        self.repo = AsyncPushRepository()

    def get_vapid_key(self) -> Dict[str, str]:
        pub_key = PushPolicy.assert_vapid_configured()
        return {"public_key": pub_key}

    async def _cleanup_stale_subscriptions(self, user_id: str) -> int:
        count = await self.repo.count_user_subscriptions(user_id)
        if count >= PushRules.MAX_SUBSCRIPTIONS_PER_USER:
            to_remove = count - PushRules.MAX_SUBSCRIPTIONS_PER_USER + 1
            stale_ids = await self.repo.get_stale_subscriptions(user_id, to_remove)
            if stale_ids:
                await self.repo.delete_subscriptions(stale_ids)
                return len(stale_ids)
        return 0

    async def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> Dict[str, Any]:
        PushPolicy.assert_valid_endpoint(endpoint)
        
        if await self.repo.is_duplicate_subscription(user_id, endpoint):
            return {"message": "Already subscribed", "cleaned": 0}

        cleaned = await self._cleanup_stale_subscriptions(user_id)
        sub_json = json.dumps({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}})

        await self.repo.upsert_subscription(user_id, endpoint, sub_json)
        return {"message": PushMessages.SUBSCRIBED, "cleaned": cleaned}

    async def unsubscribe(self, endpoint: str) -> None:
        await self.repo.delete_subscription_by_endpoint(endpoint)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        count = await self.repo.count_user_subscriptions(user_id)
        return {
            "subscribed": count > 0, 
            "subscription_count": count, 
            "max_allowed": PushRules.MAX_SUBSCRIPTIONS_PER_USER, 
            "vapid_configured": bool(VAPID_PUBLIC_KEY)
        }

    # 🔥 ENTERPRISE UPGRADE: Bounded Concurrent Scatter-Gather Dispatch
    async def send_batch_notification(self, user_ids: List[str], title: str, body: str, icon: str, url: str) -> Dict[str, Any]:
        PushPolicy.assert_valid_batch_size(user_ids)
        
        results: Dict[str, Any] = {"success": 0, "failed": 0, "details": []}
        semaphore = asyncio.Semaphore(20)  # Limit concurrent outbound HTTP sockets to 20

        async def _bounded_send(uid: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    sent = await send_push_to_user(user_id=uid, title=title, body=body, icon=icon, url=url)
                    if sent > 0:
                        return {"user_id": uid, "status": "sent", "success": True}
                    return {"user_id": uid, "status": "no_subscription", "success": False}
                except Exception as exc:
                    logger.warning("Push dispatch failed for user %s: %s", uid[:8], str(exc)[:100])
                    return {"user_id": uid, "status": f"error: {str(exc)[:100]}", "success": False}

        # Execute all notifications concurrently
        tasks = [_bounded_send(uid) for uid in user_ids]
        batch_outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in batch_outcomes:
            if isinstance(outcome, Exception):
                results["failed"] += 1
                results["details"].append({"user_id": "unknown", "status": "unhandled_exception"})
            else:
                if outcome["success"]:
                    results["success"] += 1
                else:
                    results["failed"] += 1
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