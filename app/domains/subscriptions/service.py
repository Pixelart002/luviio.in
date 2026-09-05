"""
Subscription Domain — Service
==============================
Path: app/domains/subscriptions/service.py

Effective tier resolution:
  1. Active `user_subscriptions` row (highest ends_at) -> its plan tier.
  2. Else fall back to `user.tier` (legacy column) normalized.
  3. Else "free".

`get_tier_for_user` is the single source other domains use to know what a
user may access (premium/platinum-gated products, free shipping, discounts).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException

from app.domains.subscriptions.repository import AsyncSubscriptionRepository
from app.domains.subscriptions.policy import SubscriptionPolicy
from app.domains.subscriptions.tier_registry import (
    all_tiers_public, get_tier_perks, normalize_tier, render_tier,
)

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self) -> None:
        self.repo = AsyncSubscriptionRepository()

    # ── Public tiers ───────────────────────────────────────────────────────────
    async def public_tiers(self) -> List[dict[str, Any]]:
        return all_tiers_public()

    async def list_plans(self, include_inactive: bool = False) -> List[dict[str, Any]]:
        return await self.repo.list_plans(active_only=not include_inactive)

    # ── Effective tier for a user (SSOT consumers call this) ───────────────────
    async def get_tier_for_user(
        self, user_id: Optional[str], user: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Returns {tier, plan_id, plan_name, ends_at, perks} with graceful
        fallback to user.tier / free when no paid subscription is found."""
        fallback = normalize_tier((user or {}).get("tier")) if user else "free"

        if not user_id:
            return self._tier_result(fallback, perks=get_tier_perks(fallback))

        sub = await self.repo.get_active_for_user(user_id)
        if not sub:
            return self._tier_result(fallback, perks=get_tier_perks(fallback))

        tier = normalize_tier(sub.get("tier") or (await self._plan_tier(sub.get("plan_id"))) or fallback)
        return self._tier_result(
            tier,
            plan_id=sub.get("plan_id"),
            plan_name=sub.get("plan_name"),
            ends_at=sub.get("ends_at"),
            perks=get_tier_perks(tier),
        )

    async def _plan_tier(self, plan_id: Optional[str]) -> Optional[str]:
        if not plan_id:
            return None
        plan = await self.repo.get_plan(plan_id)
        return plan.get("tier") if plan else None

    @staticmethod
    def _tier_result(tier: str, **extras: Any) -> dict[str, Any]:
        return {"tier": tier, "perks": render_tier(tier), **extras}

    # ── Plan CRUD (admin) ──────────────────────────────────────────────────────
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

    # ── Subscribe (simulated grant; real flow connects to Stripe/Payment later) ─
    async def subscribe(self, user_id: str, plan_id: str) -> Dict[str, Any]:
        plan = await self.repo.get_plan(plan_id)
        SubscriptionPolicy.assert_plan(plan)
        SubscriptionPolicy.assert_plan_active(plan)

        now = datetime.now(timezone.utc)
        days = int(plan.get("duration_days") or 30)
        sub = await self.repo.upsert_subscription({
            "id": str(uuid4()),
            "user_id": user_id,
            "plan_id": plan["id"],
            "plan_name": plan.get("name"),
            "tier": plan["tier"],
            "status": "active",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=days)).isoformat(),
        })
        if not sub:
            raise HTTPException(status_code=500, detail="Failed to start subscription.")
        return sub
