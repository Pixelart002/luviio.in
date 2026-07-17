"""
Push Notification Service — Enterprise Dispatch & Ledger Management
=================================================================
Path: app/services/push_service.py
"""
import json
import logging
from typing import Dict, Any, List
from fastapi import HTTPException, status

from app.repositories.push_repo import AsyncPushRepository
from app.permissions.policies.push_policies import PushPolicy
from app.constants.push_messages import PushMessages, PushSecurityMessages
from app.core.config import settings
from app.integrations.push.webpush_impl import send_webpush_notification # Assuming this handles pywebpush

logger = logging.getLogger(__name__)

class PushService:
    def __init__(self):
        self.repo = AsyncPushRepository()
        self.vapid_public_key = getattr(settings, "VAPID_PUBLIC_KEY", None)

    def get_vapid_key(self) -> Dict[str, str]:
        if not self.vapid_public_key:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=PushSecurityMessages.VAPID_NOT_CONFIGURED)
        return {"public_key": self.vapid_public_key}

    async def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> Dict[str, Any]:
        """Registers a new push device. Enforces ABAC max device limits."""
        endpoint_str = str(endpoint)
        PushPolicy.assert_valid_endpoint(endpoint_str)

        is_dup = await self.repo.is_duplicate_subscription(user_id, endpoint_str)
        cleaned = 0

        if not is_dup:
            current_count = await self.repo.count_user_subscriptions(user_id)
            stale_count = PushPolicy.get_stale_cleanup_target(current_count, max_limit=5)
            
            if stale_count > 0:
                stale_ids = await self.repo.get_stale_subscriptions(user_id, stale_count)
                await self.repo.delete_subscriptions(stale_ids)
                cleaned = len(stale_ids)

        subscription_json = json.dumps({"endpoint": endpoint_str, "keys": {"p256dh": p256dh, "auth": auth}})
        await self.repo.upsert_subscription(user_id, endpoint_str, subscription_json)

        return {"message": PushMessages.SUBSCRIBED, "cleaned": cleaned}

    async def unsubscribe(self, endpoint: str) -> None:
        """Silently removes endpoint from ledger."""
        endpoint_str = str(endpoint)
        await self.repo.delete_subscription_by_endpoint(endpoint_str)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        count = await self.repo.count_user_subscriptions(user_id)
        return {
            "subscribed": count > 0,
            "subscription_count": count,
            "max_allowed": 5,
            "vapid_configured": bool(self.vapid_public_key)
        }

    async def send_batch_notification(self, user_ids: List[str], title: str, body: str, icon: str, url: str) -> Dict[str, Any]:
        """Dispatches payload to multiple targets. Intended for PBAC Admin use."""
        targets = await self.repo.get_endpoints_for_users(user_ids)
        success, failed = 0, 0
        details = []

        # Here we mock the dispatch process. In reality, it calls pywebpush synchronously/async.
        for target in targets:
            try:
                sub_info = json.loads(target["subscription_json"])
                await send_webpush_notification(sub_info, {"title": title, "body": body, "icon": icon, "url": url})
                success += 1
            except Exception as e:
                failed += 1
                details.append({"user_id": target["user_id"], "error": str(e)})
                # Auto-cleanup failed/expired endpoints
                if "410 Gone" in str(e) or "404" in str(e):
                    await self.repo.delete_subscription_by_endpoint(target["endpoint"])

        return {"success": success, "failed": failed, "details": details}

    async def get_stats(self) -> Dict[str, Any]:
        total = await self.repo.get_total_subscriptions_count()
        unique = await self.repo.get_unique_subscribed_users()
        return {
            "total_subscriptions": total,
            "unique_users": unique,
            "avg_per_user": round(total / unique, 2) if unique > 0 else 0.0,
            "vapid_configured": bool(self.vapid_public_key)
        }