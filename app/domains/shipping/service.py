"""
Shipping Domain — Service
==========================
"""
from __future__ import annotations

import asyncio
import logging
import math
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
        ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
        activated = await self.repo.activate_atomic(method_id)
        if not activated:
            raise HTTPException(status_code=500, detail="Failed to activate shipping method safely.")
        return activated

    @staticmethod
    def _number(value: Any, field_name: str) -> float:
        try:
            number = float(str(value).strip().replace("'", "").replace('"', ""))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=f"Invalid shipping configuration: {field_name}.") from exc
        if not math.isfinite(number) or number < 0:
            raise HTTPException(status_code=503, detail=f"Invalid shipping configuration: {field_name}.")
        return number

    @staticmethod
    def _enabled(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        normalized = str(value).strip().lower().replace("'", "").replace('"', "")
        if normalized == "true":
            return True
        if normalized == "false":
            return False
        raise HTTPException(status_code=503, detail="Invalid shipping configuration: shipping_enabled.")

    async def compute_rate(
        self,
        subtotal: float,
        item_count: int = 1,
        weight_kg: float = 0.0,
        method_id: Optional[str] = None,
        pincode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not math.isfinite(float(subtotal)) or float(subtotal) < 0:
            raise HTTPException(status_code=422, detail="Invalid cart subtotal.")
        if item_count < 1 or not math.isfinite(float(weight_kg)) or float(weight_kg) < 0:
            raise HTTPException(status_code=422, detail="Invalid shipping quantity or weight.")

        settings = SettingsCoreEngine()
        try:
            shipping_enabled_raw, threshold_raw, flat_raw = await asyncio.gather(
                settings.fetch_by_key("shipping_enabled"),
                settings.fetch_by_key("free_shipping_threshold"),
                settings.fetch_by_key("flat_shipping_rate"),
            )
            shipping_enabled = self._enabled(shipping_enabled_raw)
            threshold = self._number(threshold_raw, "free_shipping_threshold")
            base = self._number(flat_raw, "flat_shipping_rate")
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("[SHIPPING] required shipping settings unavailable")
            raise HTTPException(
                status_code=503,
                detail="Shipping configuration is temporarily unavailable.",
            ) from exc

        method: Optional[Dict[str, Any]] = None
        if method_id:
            method = ShippingPolicy.assert_method(await self.repo.get_by_id(method_id))
            if not method.get("is_active", True):
                raise HTTPException(status_code=400, detail="This shipping method is inactive.")
        else:
            method = await self._pick_active_method()

        if not shipping_enabled:
            return {
                "shipping_cost": 0.0,
                "method": method,
                "method_id": method.get("id") if method else None,
                "free_shipping_threshold": threshold,
                "applied_type": "disabled",
            }

        # Explicit method selection is supported for advanced callers. Normal
        # checkout remains settings-driven so stale method rates cannot silently
        # replace the canonical store shipping configuration.
        if method_id and method is not None:
            result = self._compute_method_rate(method, subtotal, item_count, weight_kg)
            result["free_shipping_threshold"] = threshold
            return result

        shipping = 0.0 if subtotal >= threshold else base
        return {
            "shipping_cost": round(shipping, 2),
            "method": method,
            "method_id": method.get("id") if method else None,
            "free_shipping_threshold": threshold,
            "applied_type": "settings_default",
        }

    @staticmethod
    def _compute_method_rate(
        method: dict[str, Any], subtotal: float, item_count: int, weight_kg: float
    ) -> Dict[str, Any]:
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
        return methods[0] if methods else None
