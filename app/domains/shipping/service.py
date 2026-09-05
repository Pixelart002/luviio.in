"""
Shipping Domain — Service
==========================
Path: app/domains/shipping/service.py
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.domains.shipping.repository import AsyncShippingRepository
from app.domains.shipping.policy import ShippingPolicy
from app.constants.shipping_messages import (
    SHIPPING_FLAT, SHIPPING_FREE_THRESHOLD, SHIPPING_PER_ITEM, SHIPPING_WEIGHT,
)

logger = logging.getLogger(__name__)


class ShippingService:
    def __init__(self) -> None:
        self.repo = AsyncShippingRepository()

    # ── Admin CRUD ───────────────────────────────────────────────────────────
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

    # ── Rate computation ─────────────────────────────────────────────────────
    async def compute_rate(self, subtotal: float, item_count: int = 1,
                           weight_kg: float = 0.0, method_id: Optional[str] = None,
                           pincode: Optional[str] = None) -> Dict[str, Any]:
        if method_id:
            method = await self.repo.get_by_id(method_id)
            ShippingPolicy.assert_method(method)
            if not method.get("is_active", True):
                raise HTTPException(status_code=400, detail="This shipping method is inactive.")
            return self._compute_method_rate(method, subtotal, item_count, weight_kg)

        # No explicit method -> fall back to dynamic store settings (safe default,
        # identical to the legacy order-flow formula: free above threshold).
        from app.services.settings.core_engine import SettingsCoreEngine
        settings = SettingsCoreEngine()
        try:
            threshold = float(str(await settings.fetch_by_key("free_shipping_threshold")).replace("'", "").replace('"', "") or 1499.0)
        except Exception:
            threshold = 1499.0
        try:
            base = float(str(await settings.fetch_by_key("standard_shipping_cost")).replace("'", "").replace('"', "") or 45.90)
        except Exception:
            base = 45.90

        shipping = 0.0 if subtotal >= threshold else base
        method = await self._pick_fallback_method()
        return {
            "shipping_cost": round(shipping, 2),
            "method": method,
            "method_id": method.get("id") if method else None,
            "free_shipping_threshold": threshold,
            "applied_type": "settings_default",
        }

    def _compute_method_rate(self, method: dict[str, Any], subtotal: float,
                             item_count: int, weight_kg: float) -> Dict[str, Any]:
        mtype = method["type"]
        if mtype == SHIPPING_FLAT:
            cost = float(method.get("base_rate") or 0)
        elif mtype == SHIPPING_FREE_THRESHOLD:
            threshold = float(method.get("threshold") or 0)
            cost = 0.0 if threshold and subtotal >= threshold else float(method.get("base_rate") or 0)
        elif mtype == SHIPPING_PER_ITEM:
            cost = float(method.get("base_rate") or 0) + float(method.get("per_item_rate") or 0) * item_count
        elif mtype == SHIPPING_WEIGHT:
            cost = float(method.get("base_rate") or 0) + float(method.get("weight_rate") or 0) * weight_kg
        else:
            cost = float(method.get("base_rate") or 0)
        return {
            "shipping_cost": round(max(0.0, cost), 2),
            "method": method,
            "method_id": method.get("id"),
            "applied_type": mtype,
        }

    async def _pick_fallback_method(self) -> Optional[Dict[str, Any]]:
        methods = await self.repo.list_active_methods()
        if not methods:
            return None
        # Prefer the flat method as the "standard" fallback; else the first.
        for m in methods:
            if m.get("type") == SHIPPING_FLAT:
                return m
        return methods[0]
