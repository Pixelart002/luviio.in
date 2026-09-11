"""
Shipping Domain — Service
==========================
"""
from __future__ import annotations

import logging
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
        requested_active = bool(payload.get("is_active", True))
        payload["is_active"] = False

        method = await self.repo.create(payload)
        if not method:
            raise HTTPException(status_code=500, detail="Failed to create shipping method.")

        if requested_active:
            return await self.activate(str(method["id"]))
        return method

    async def update(self, method_id: str, payload: dict[str, Any]) -> Dict[str, Any]:
        existing = ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
        if "type" in payload:
            ShippingPolicy.assert_valid_type(payload["type"])

        requested_active = payload.pop("is_active", None)
        if requested_active is True:
            updated = await self.repo.update(method_id, payload) if payload else existing
            if not updated:
                raise HTTPException(status_code=500, detail="Failed to update shipping method.")
            return await self.activate(method_id)

        if requested_active is False and existing.get("is_active", False):
            raise HTTPException(
                status_code=409,
                detail="The active shipping method cannot be disabled. Activate another method first.",
            )

        updated = await self.repo.update(method_id, payload)
        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update shipping method.")
        return updated

    async def activate(self, method_id: str) -> Dict[str, Any]:
        target = ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
        if target.get("is_active"):
            return target

        methods = await self.repo.list_all()
        # Switch semantics: deactivate the current method(s), then activate target.
        for method in methods:
            current_id = str(method.get("id"))
            if current_id != method_id and method.get("is_active"):
                changed = await self.repo.set_active(current_id, False)
                if changed is None:
                    raise HTTPException(status_code=500, detail="Failed to switch shipping method safely.")

        activated = await self.repo.set_active(method_id, True)
        if activated is None:
            raise HTTPException(status_code=500, detail="Failed to activate shipping method.")
        return activated

    async def compute_rate(self, subtotal: float, item_count: int = 1,
                           weight_kg: float = 0.0, method_id: Optional[str] = None,
                           pincode: Optional[str] = None) -> Dict[str, Any]:
        if method_id:
            method = await self.repo.get_by_id(method_id)
            ShippingPolicy.assert_method(method)
            if not method.get("is_active", True):
                raise HTTPException(status_code=400, detail="This shipping method is inactive.")
            return self._compute_method_rate(method, subtotal, item_count, weight_kg)

        settings = SettingsCoreEngine()
        try:
            threshold = float(str(await settings.fetch_by_key("free_shipping_threshold")).replace("'", "").replace('"', ""))
            base = float(str(await settings.fetch_by_key("standard_shipping_cost")).replace("'", "").replace('"', ""))
        except Exception as exc:
            logger.exception("[SHIPPING] required shipping settings unavailable")
            raise HTTPException(
                status_code=503,
                detail="Shipping configuration is temporarily unavailable.",
            ) from exc

        shipping = 0.0 if subtotal >= threshold else base
        method = await self._pick_active_method()
        if method is None:
            raise HTTPException(status_code=503, detail="No active shipping method is configured.")
        return {
            "shipping_cost": round(shipping, 2),
            "method": method,
            "method_id": method.get("id"),
            "free_shipping_threshold": threshold,
            "applied_type": "settings_default",
        }

    @staticmethod
    def _compute_method_rate(method: dict[str, Any], subtotal: float,
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

    async def _pick_active_method(self) -> Optional[Dict[str, Any]]:
        methods = await self.repo.list_active_methods()
        if not methods:
            return None
        return methods[0]
