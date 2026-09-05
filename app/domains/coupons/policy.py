"""
Coupons Domain — Policy
========================
Path: app/domains/coupons/policy.py
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.constants.coupon_messages import CouponSecurityMessages

logger = logging.getLogger(__name__)


class CouponPolicy:
    @staticmethod
    def assert_applicable(coupon: Optional[dict[str, Any]], subtotal: float, user_type: str = "customer") -> dict[str, Any]:
        """ABAC guard — validity, window, min-order, activity."""
        if not coupon:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CouponSecurityMessages.NOT_FOUND)
        if not coupon.get("is_active", False):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.INACTIVE)

        now = datetime.now(timezone.utc)

        def _parse(v):
            if not v:
                return None
            if isinstance(v, datetime):
                return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
            return v

        valid_from = _parse(coupon.get("valid_from"))
        valid_until = _parse(coupon.get("valid_until"))

        if valid_from and now < valid_from:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.NOT_STARTED)
        if valid_until and now > valid_until:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.EXPIRED)

        min_order = float(coupon.get("min_order_amount") or 0)
        if subtotal < min_order:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.MIN_ORDER_NOT_MET)

        return coupon

    @staticmethod
    def assert_limits(coupon: dict[str, Any], user_used: int) -> None:
        usage_limit = coupon.get("usage_limit")
        if usage_limit is not None:
            if int(coupon.get("used_count") or 0) >= int(usage_limit):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.USAGE_LIMIT_REACHED)
        per_user = int(coupon.get("per_user_limit") or 1)
        if user_used >= per_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CouponSecurityMessages.USER_LIMIT_REACHED)
