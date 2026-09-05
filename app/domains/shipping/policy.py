"""
Shipping Domain — Policy
=========================
Path: app/domains/shipping/policy.py
"""
from typing import Any, Optional

from fastapi import HTTPException, status

from app.constants.shipping_messages import ShippingSecurityMessages


class ShippingPolicy:
    @staticmethod
    def assert_method(method: Optional[dict[str, Any]]) -> dict[str, Any]:
        if not method:
            raise HTTPException(status_code=404, detail=ShippingSecurityMessages.METHOD_NOT_FOUND)
        return method

    @staticmethod
    def assert_valid_type(method_type: str) -> None:
        from app.constants.shipping_messages import (
            SHIPPING_FLAT, SHIPPING_FREE_THRESHOLD, SHIPPING_PER_ITEM, SHIPPING_WEIGHT,
        )
        if method_type not in (SHIPPING_FLAT, SHIPPING_FREE_THRESHOLD, SHIPPING_PER_ITEM, SHIPPING_WEIGHT):
            raise HTTPException(status_code=400, detail=ShippingSecurityMessages.INVALID_TYPE)
