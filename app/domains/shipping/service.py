"""
Shipping Domain — Service
==========================
Path: app/domains/shipping/service.py
"""
from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.constants.shipping_messages import (
    SHIPPING_FLAT,
    SHIPPING_FREE_THRESHOLD,
    SHIPPING_PER_ITEM,
    SHIPPING_WEIGHT,
)
from app.domains.settings.core_engine import SettingsCoreEngine
from app.domains.shipping.policy import ShippingPolicy
from app.domains.shipping.repository import AsyncShippingRepository

logger = logging.getLogger(__name__)


class ShippingService:
    def __init__(self) -> None:
        self.repo = AsyncShippingRepository()

    async def list_methods(self, active_only: bool) -> List[Dict[str, Any]]:
        return await self.repo.list_active_methods() if active_only else await self.repo.list_all()

    async def create(self, payload: dict[str, Any]) -> Dict[str, Any]:
        ShippingPolicy.assert_valid_type(payload["type"])
        method = await self.repo.create(payload)
        if not method:
            raise HTTPException(status_code=500, detail="Failed to create shipping method.")
        return method

    async def update(self, method_id: str, payload: dict[str, Any]) -> Dict[str, Any]:
        ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
        updated = await self.repo.update(method_id, payload)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update shipping method.")
        return updated

    async def delete(self, method_id: str) -> None:
        ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
        await self.repo.delete(method_id)

    async def compute_rate(self, subtotal: Decimal, item_count: int = 1,
                           weight_kg: Decimal = Decimal("0"), method_id: Optional[str] = None,
                           pincode: Optional[str] = None, volumetric_weight_kg: Decimal = Decimal("0"),
                           cod: bool = False) -> Dict[str, Any]:
        if method_id:
            method = await self.repo.get_by_id(method_id)
            ShippingPolicy.assert_method(method)
            if not method.get("is_active", True):
                raise HTTPException(status_code=400, detail="This shipping method is inactive.")
            if cod and not method.get("supports_cod", True):
                raise HTTPException(status_code=400, detail="Selected shipping method does not support COD")
            return self._compute_method_rate(method, subtotal, item_count, max(weight_kg, volumetric_weight_kg))

        settings = SettingsCoreEngine()
        try:
            threshold = float(str(await settings.fetch_by_key("free_shipping_threshold")).replace("'", "").replace('"', "") or 1499.0)
        except Exception:
            threshold = 1499.0
        try:
            base = float(str(await settings.fetch_by_key("standard_shipping_cost")).replace("'", "").replace('"', "") or 45.90)
        except Exception:
            base = 45.90

        shipping = Decimal("0") if subtotal >= Decimal(str(threshold)) else Decimal(str(base))
        method = await self._pick_fallback_method()
        return {
            "shipping_cost": shipping.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "method": method,
            "method_id": method.get("id") if method else None,
            "free_shipping_threshold": threshold,
            "applied_type": "settings_default",
        }

    @staticmethod
    def _compute_method_rate(method: dict[str, Any], subtotal: Decimal,
                             item_count: int, weight_kg: Decimal) -> Dict[str, Any]:
        mtype = method["type"]
        if mtype == SHIPPING_FLAT:
            cost = Decimal(str(method.get("base_rate") or 0))
        elif mtype == SHIPPING_FREE_THRESHOLD:
            threshold = Decimal(str(method.get("threshold") or 0))
            cost = Decimal("0") if threshold and subtotal >= threshold else Decimal(str(method.get("base_rate") or 0))
        elif mtype == SHIPPING_PER_ITEM:
            cost = Decimal(str(method.get("base_rate") or 0)) + Decimal(str(method.get("per_item_rate") or 0)) * item_count
        elif mtype == SHIPPING_WEIGHT:
            cost = Decimal(str(method.get("base_rate") or 0)) + Decimal(str(method.get("weight_rate") or 0)) * weight_kg
        else:
            cost = Decimal(str(method.get("base_rate") or 0))
        return {
            "shipping_cost": max(Decimal("0"), cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "method": method,
            "method_id": method.get("id"),
            "applied_type": mtype,
        }

    async def _pick_fallback_method(self) -> Optional[Dict[str, Any]]:
        methods = await self.repo.list_active_methods()
        if not methods:
            return None
        for m in methods:
            if m.get("type") == SHIPPING_FLAT:
                return m
        return methods[0]
