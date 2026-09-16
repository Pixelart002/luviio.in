"""
Subscription Domain — Service
==============================
Path: app/domains/subscriptions/service.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException

from app.domains.notifications.service import PushService
from app.domains.subscriptions.policy import SubscriptionPolicy
from app.domains.subscriptions.repository import AsyncSubscriptionRepository
from app.domains.subscriptions.tier_registry import all_tiers_public, get_tier_perks, normalize_tier, render_tier

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self) -> None:
        self.repo = AsyncSubscriptionRepository()

    async def public_tiers(self) -> List[dict[str, Any]]:
        return all_tiers_public()

    async def list_plans(self, active_only: bool = True) -> List[dict[str, Any]]:
        return await self.repo.list_plans(active_only=active_only)

    async def get_tier_for_user(self, user_id: Optional[str], user: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        fallback = normalize_tier((user or {}).get("tier")) if user else "free"
        if not user_id:
            return self._tier_result(fallback, perks=get_tier_perks(fallback))
        sub = await self.repo.get_active_for_user(user_id)
        if not sub:
            return self._tier_result(fallback, perks=get_tier_perks(fallback))
        tier = normalize_tier(sub.get("tier") or (await self._plan_tier(sub.get("plan_id"))) or fallback)
        return self._tier_result(tier, plan_id=sub.get("plan_id"), plan_name=sub.get("plan_name"), ends_at=sub.get("ends_at"), perks=get_tier_perks(tier))

    async def _plan_tier(self, plan_id: Optional[str]) -> Optional[str]:
        if not plan_id:
            return None
        plan = await self.repo.get_plan(plan_id)
        return plan.get("tier") if plan else None

    @staticmethod
    def _tier_result(tier: str, **extras: Any) -> dict[str, Any]:
        return {"tier": tier, "perks": render_tier(tier), **extras}

    async def create_plan(self, payload: dict[str, Any]) -> Dict[str, Any]:
        tier = SubscriptionPolicy.assert_valid_tier(payload["tier"])
        plan = await self.repo.create_plan({**payload, "tier": tier})
        if not plan:
            raise HTTPException(status_code=500, detail="Failed to create subscription plan.")
        return plan

    async def update_plan(self, plan_id: str, payload: dict[str, Any]) -> Dict[str, Any]:
        plan = await self.repo.get_plan(plan_id)
        SubscriptionPolicy.assert_plan(plan)
        if "tier" in payload:
            payload["tier"] = SubscriptionPolicy.assert_valid_tier(payload["tier"])
        updated = await self.repo.update_plan(plan_id, payload)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update subscription plan.")
        return updated

    async def subscribe(self, user_id: str, plan_id: str) -> Dict[str, Any]:
        plan = await self.repo.get_plan(plan_id)
        SubscriptionPolicy.assert_plan(plan)
        SubscriptionPolicy.assert_plan_active(plan)
        existing = await self.repo.get_active_for_user(user_id)
        if existing:
            raise HTTPException(status_code=409, detail="User already has an active subscription.")
        now = datetime.now(timezone.utc)
        days = int(plan.get("duration_days") or 30)
        sub = await self.repo.upsert_subscription({
            "id": str(uuid4()), "user_id": user_id, "plan_id": plan["id"],
            "plan_name": plan.get("name"), "tier": plan["tier"], "status": "active",
            "starts_at": now.isoformat(), "ends_at": (now + timedelta(days=days)).isoformat(),
        })
        if not sub:
            raise HTTPException(status_code=500, detail="Failed to start subscription.")
        return sub

    async def cancel(self, user_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        sub = await self.repo.get_active_for_user(user_id)
        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found.")
        now = datetime.now(timezone.utc).isoformat()
        data: dict[str, Any] = {"status": "cancelled", "cancelled_at": now}
        if reason:
            data["cancellation_reason"] = reason
        updated = await self.repo.cancel_subscription(sub["id"], data)
        if not updated:
            raise HTTPException(status_code=409, detail="Subscription could not be cancelled.")
        return updated

    async def generate_due_reminders(self, now: Optional[datetime] = None) -> Dict[str, int]:
        now = now or datetime.now(timezone.utc)
        rows = await self.repo.list_due_reminder_subscriptions(now + timedelta(days=7))
        created = 0
        for sub in rows:
            ends_at = datetime.fromisoformat(str(sub["ends_at"]).replace("Z", "+00:00"))
            if ends_at <= now:
                reminder_type = "expired"
                title = "Luviio membership expired"
                body = "Your membership has expired. Renew manually to continue your membership benefits."
            elif ends_at <= now + timedelta(days=1):
                reminder_type = "1d"
                title = "Luviio membership expires tomorrow"
                body = "Your membership expires tomorrow. Renew manually to keep your membership active."
            else:
                reminder_type = "7d"
                title = "Luviio membership expires soon"
                body = "Your membership expires in 7 days. Renew manually when you are ready."
            row = await self.repo.create_reminder_if_missing({
                "subscription_id": sub["id"], "user_id": sub["user_id"],
                "reminder_type": reminder_type, "due_at": ends_at.isoformat(),
                "title": title, "body": body,
            })
            if row:
                created += 1
        return {"subscriptions_checked": len(rows), "reminders_created": created}

    async def dispatch_pending_reminders(self) -> Dict[str, int]:
        pending = await self.repo.list_pending_reminders()
        push = PushService()
        sent = 0
        for reminder in pending:
            try:
                count = await push.repo.count_user_subscriptions(str(reminder["user_id"]))
                if count:
                    await push.send_batch_notification(
                        [str(reminder["user_id"])], reminder["title"], reminder["body"], "/icon-192.png", "/account/subscription"
                    )
                if await self.repo.mark_reminder_sent(str(reminder["id"])):
                    sent += 1
            except Exception as exc:
                logger.warning("[SUB REMINDER] dispatch failed: %s", exc)
        return {"pending_checked": len(pending), "reminders_sent": sent}

    async def get_reminders(self, user_id: str) -> List[dict[str, Any]]:
        return await self.repo.list_user_reminders(user_id)

    async def dismiss_reminder(self, user_id: str, reminder_id: str) -> None:
        if not await self.repo.dismiss_reminder(user_id, reminder_id):
            raise HTTPException(status_code=404, detail="Reminder not found.")
