"""
Subscription Domain — Policy
=============================
Path: app/domains/subscriptions/policy.py
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException, status

from app.constants.subscription_messages import SubscriptionSecurityMessages
from app.domains.subscriptions.tier_registry import TIER_ORDER, normalize_tier


class SubscriptionPolicy:
    @staticmethod
    def assert_valid_tier(tier: str) -> str:
        normalized = normalize_tier(tier)
        if normalized not in TIER_ORDER:
            raise HTTPException(status_code=400, detail=SubscriptionSecurityMessages.INVALID_TIER)
        return normalized

    @staticmethod
    def assert_plan(plan: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not plan:
            raise HTTPException(status_code=404, detail=SubscriptionSecurityMessages.PLAN_NOT_FOUND)
        return plan

    @staticmethod
    def assert_plan_active(plan: dict[str, Any]) -> dict[str, Any]:
        if not plan.get("is_active", True):
            raise HTTPException(status_code=400, detail=SubscriptionSecurityMessages.PLAN_INACTIVE)
        return plan

    @staticmethod
    def assert_can_access_tier(user_tier: str, target_tier: str) -> None:
        from app.domains.subscriptions.tier_registry import tier_rank
        if tier_rank(user_tier) < tier_rank(target_tier):
            raise HTTPException(
                status_code=403,
                detail=SubscriptionSecurityMessages.TIER_REQUIRED.format(
                    target=target_tier,
                    current=normalize_tier(user_tier),
                ),
            )
