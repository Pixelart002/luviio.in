"""
Coupons Domain — Service
========================
Path: app/domains/coupons/service.py
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, status

from app.domains.coupons.repository import AsyncCouponRepository
from app.domains.coupons.policy import CouponPolicy
from app.constants.coupon_messages import COUPON_TYPE_PERCENT, CouponSecurityMessages
from app.permissions.action_control import assert_action_enabled

logger = logging.getLogger(__name__)

_SERIALIZABLE_FIELDS = (
    "id", "code", "type", "value", "min_order_amount", "max_discount",
    "valid_from", "valid_until", "usage_limit", "per_user_limit",
    "used_count", "is_active", "description", "created_at",
)


class CouponService:
    def __init__(self) -> None:
        self.repo = AsyncCouponRepository()

    # ── Admin CRUD ───────────────────────────────────────────────────────────
    async def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = await self.repo.get_by_code(payload["code"])
        if existing is not None:
            raise HTTPException(status_code=400, detail="Coupon code already exists.")
        data = {k: payload.get(k) for k in (
            "code", "type", "value", "min_order_amount", "max_discount",
            "valid_from", "valid_until", "usage_limit", "per_user_limit",
            "is_active", "description",
        )}
        data.setdefault("used_count", 0)
        created = await self.repo.create(data)
        if not created:
            raise HTTPException(status_code=500, detail="Failed to create coupon.")
        return {k: created.get(k) for k in _SERIALIZABLE_FIELDS}

    async def update(self, coupon_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        coupon = await self.repo.get_by_id(coupon_id)
        if not coupon:
            raise HTTPException(status_code=404, detail=CouponSecurityMessages.NOT_FOUND)
        data = {k: v for k, v in payload.items() if v is not None}
        updated = await self.repo.update(coupon_id, data)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update coupon.")
        return {k: updated.get(k) for k in _SERIALIZABLE_FIELDS}

    async def delete(self, coupon_id: str) -> None:
        coupon = await self.repo.get_by_id(coupon_id)
        if not coupon:
            raise HTTPException(status_code=404, detail=CouponSecurityMessages.NOT_FOUND)
        await self.repo.delete(coupon_id)

    async def list_all(self, page: int, page_size: int) -> Tuple[list, int]:
        return await self.repo.list_all(page, page_size)

    # ── Customer apply / validate ────────────────────────────────────────────
    async def apply(self, code: str, cart_subtotal: float, user_id: str, order_id: str = "") -> Dict[str, Any]:
        # Per-user capability gate: an admin can disable coupon use for a user.
        await assert_action_enabled(user_id, "apply_coupon",
                                    "Applying coupons has been disabled for your account.")

        coupon = await self.repo.get_by_code(code)
        CouponPolicy.assert_applicable(coupon, cart_subtotal)

        used = await self.repo.redemptions_for_user(coupon["id"], user_id)
        CouponPolicy.assert_limits(coupon, used)

        discount = self._compute_discount(coupon, cart_subtotal)
        if discount <= 0:
            raise HTTPException(status_code=400, detail="This coupon yields no discount on the current cart.")

        if order_id:
            await self.repo.record_redemption(coupon["id"], user_id, order_id, discount)

        return {
            "code": coupon["code"],
            "type": coupon["type"],
            "value": float(coupon["value"]),
            "discount": round(discount, 2),
            "subtotal_after": round(max(0.0, cart_subtotal - discount), 2),
            "coupon_id": coupon["id"],
        }

    @staticmethod
    def _compute_discount(coupon: dict[str, Any], subtotal: float) -> float:
        if coupon["type"] == COUPON_TYPE_PERCENT:
            discount = subtotal * (float(coupon["value"]) / 100.0)
        else:
            discount = float(coupon["value"])
        if coupon.get("max_discount") is not None:
            discount = min(discount, float(coupon["max_discount"]))
        return min(discount, subtotal)

    # ── Public helper for the orders/payment pipeline ───────────────────────
    async def resolve_discount_for_checkout(self, code: Optional[str], cart_subtotal: float,
                                            user_id: str) -> Dict[str, Any]:
        """Returns {discount, coupon_id, code} without recording (recording happens on payment)."""
        if not code:
            return {"discount": 0.0, "coupon_id": None, "code": None}
        await assert_action_enabled(user_id, "apply_coupon")
        coupon = await self.repo.get_by_code(code)
        CouponPolicy.assert_applicable(coupon, cart_subtotal)
        used = await self.repo.redemptions_for_user(coupon["id"], user_id)
        CouponPolicy.assert_limits(coupon, used)
        discount = self._compute_discount(coupon, cart_subtotal)
        return {"discount": round(discount, 2), "coupon_id": coupon["id"], "code": coupon["code"]}
