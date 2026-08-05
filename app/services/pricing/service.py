"""
Pricing Service — SSOT Architecture (B2B, MOQ, MOV, VIP & STRICT TAX)
=====================================================================
Path: app/services/pricing/service.py

Architecture Upgrades:
  ✅ STRICT MODE — If GST%, Price, or Qty is missing, it crashes (Halt Order).
  ✅ DB Toggles Respected — tax_enabled and shipping_enabled perfectly handled.
  ✅ VIP/Premium Tiers — Dynamic free shipping for 'premium' users.
  ✅ MOQ & MOV — Halts checkout if below Minimum Quantity or Minimum Value.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  VALUE OBJECT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PriceBreakdown:
    subtotal: Decimal
    shipping: Decimal
    tax:      Decimal
    total:    Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "subtotal":      float(round(self.subtotal, 2)),
            "shipping_cost": float(round(self.shipping, 2)),
            "tax_amount":    float(round(self.tax,      2)),
            "total_amount":  float(round(self.total,    2)),
            "currency":      self.currency,
        }

    @property
    def shipping_is_free(self) -> bool:
        return self.shipping == Decimal("0")

# ══════════════════════════════════════════════════════════════════════════════
#  ABSTRACT STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

class PricingStrategy(ABC):
    @abstractmethod
    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown: ...

    @property
    @abstractmethod
    def shipping_enabled(self) -> bool: ...

    @property
    @abstractmethod
    def shipping_threshold(self) -> Decimal: ...

    @property
    @abstractmethod
    def tax_rate(self) -> Decimal: ...

    @property
    @abstractmethod
    def currency(self) -> str: ...

# ══════════════════════════════════════════════════════════════════════════════
#  CONCRETE STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════

class StandardPricing(PricingStrategy):
    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat:      Decimal,
        tax_rate:           Decimal,
        currency:           str,
        store_mov:          Decimal = Decimal("0")
    ) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat
        self._tax_rate  = tax_rate
        self._currency  = currency
        self._mov       = store_mov

    @property
    def shipping_enabled(self) -> bool: return self._flat > Decimal("0") or self._threshold > Decimal("0")
    @property
    def shipping_threshold(self) -> Decimal: return self._threshold
    @property
    def tax_rate(self) -> Decimal: return self._tax_rate
    @property
    def currency(self) -> str: return self._currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        if not items:
            raise HTTPException(status_code=400, detail="CRITICAL: Empty payload.")

        calc_subtotal = Decimal("0")
        calc_tax      = Decimal("0")

        for item in items:
            prod_data = item.get("products") or item

            if "quantity" not in item or item["quantity"] is None:
                raise HTTPException(status_code=500, detail="CRITICAL: Item quantity missing.")
            item_qty = Decimal(str(item["quantity"]))

            # 🔥 STRICT MOQ CHECK (Business Gatekeeper)
            item_moq = Decimal(str(prod_data.get("moq") or 10))
            if item_qty < item_moq:
                raise HTTPException(status_code=400, detail=f"Minimum Order Quantity for '{prod_data.get('name', 'this item')}' is {int(item_moq)}.")

            price_val = item.get("price_snapshot") or item.get("unit_price") or prod_data.get("price")
            if price_val is None:
                raise HTTPException(status_code=500, detail="CRITICAL: Product price missing.")
            item_price = Decimal(str(price_val))

            item_gst_pct = prod_data.get("gst_percentage") if prod_data.get("gst_percentage") is not None else item.get("gst_percentage")
            if item_gst_pct is None:
                raise HTTPException(status_code=500, detail="CRITICAL: GST percentage missing.")
            
            item_tax_rate = Decimal(str(item_gst_pct)) / Decimal("100")

            item["price_snapshot"]          = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = float(item_gst_pct)

            item_sub = item_price * item_qty
            item_tax = item_sub * item_tax_rate

            calc_subtotal += item_sub
            calc_tax      += item_tax

        # 🔥 STRICT MOV CHECK (Business Gatekeeper)
        if calc_subtotal > Decimal("0") and calc_subtotal < self._mov:
            raise HTTPException(status_code=400, detail=f"Minimum Order Value is {self._currency} {self._mov}.")

        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if calc_subtotal >= self._threshold else self._flat
        total = calc_subtotal + shipping + calc_tax

        return PriceBreakdown(subtotal=calc_subtotal, shipping=shipping, tax=calc_tax, total=total, currency=self._currency)


class ZeroTaxPricing(PricingStrategy):
    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat:      Decimal,
        currency:           str,
        store_mov:          Decimal = Decimal("0")
    ) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat
        self._currency  = currency
        self._mov       = store_mov

    @property
    def shipping_enabled(self) -> bool: return self._flat > Decimal("0") or self._threshold > Decimal("0")
    @property
    def shipping_threshold(self) -> Decimal: return self._threshold
    @property
    def tax_rate(self) -> Decimal: return Decimal("0")
    @property
    def currency(self) -> str: return self._currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        if not items:
            raise HTTPException(status_code=400, detail="CRITICAL: Empty payload.")

        calc_subtotal = Decimal("0")

        for item in items:
            prod_data = item.get("products") or item

            if "quantity" not in item or item["quantity"] is None:
                raise HTTPException(status_code=500, detail="CRITICAL: Item quantity missing.")
            item_qty = Decimal(str(item["quantity"]))

            # 🔥 STRICT MOQ CHECK
            item_moq = Decimal(str(prod_data.get("moq") or 1))
            if item_qty < item_moq:
                raise HTTPException(status_code=400, detail=f"Minimum Order Quantity for '{prod_data.get('name', 'this item')}' is {int(item_moq)}.")

            price_val = item.get("price_snapshot") or item.get("unit_price") or prod_data.get("price")
            if price_val is None:
                raise HTTPException(status_code=500, detail="CRITICAL: Product price missing.")
            item_price = Decimal(str(price_val))

            item["price_snapshot"]          = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = float(0)

            calc_subtotal += item_price * item_qty

        # 🔥 STRICT MOV CHECK
        if calc_subtotal > Decimal("0") and calc_subtotal < self._mov:
            raise HTTPException(status_code=400, detail=f"Minimum Order Value is {self._currency} {self._mov}.")

        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if calc_subtotal >= self._threshold else self._flat
        total = calc_subtotal + shipping

        return PriceBreakdown(subtotal=calc_subtotal, shipping=shipping, tax=Decimal("0"), total=total, currency=self._currency)


class FreeShippingPricing(PricingStrategy):
    def __init__(self, base_strategy: PricingStrategy) -> None:
        self._base = base_strategy

    @property
    def shipping_enabled(self) -> bool: return False
    @property
    def shipping_threshold(self) -> Decimal: return self._base.shipping_threshold
    @property
    def tax_rate(self) -> Decimal: return self._base.tax_rate
    @property
    def currency(self) -> str: return self._base.currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        original = self._base.calculate(items=items)
        if original.subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), original.currency)

        return PriceBreakdown(
            subtotal=original.subtotal,
            shipping=Decimal("0"), # 🔥 VIP ZERO SHIPPING
            tax=original.tax,
            total=original.subtotal + original.tax,
            currency=original.currency,
        )

# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS (The Brain 🧠)
# ══════════════════════════════════════════════════════════════════════════════

def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    if not config:
        raise HTTPException(status_code=503, detail="Pricing config missing.")

    tax_enabled      = config.get("tax_enabled", True)
    shipping_enabled = config.get("shipping_enabled", True)
    currency         = config.get("currency", "INR")

    tax_rate           = Decimal(str(config.get("tax_rate", 18.0))) / Decimal("100")
    shipping_flat      = Decimal(str(config.get("shipping_flat", 99.0)))
    shipping_threshold = Decimal(str(config.get("shipping_threshold", 999.0)))
    store_mov          = Decimal(str(config.get("store_mov", 1000.0)))

    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
            currency=currency,
            store_mov=store_mov
        )

    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
            currency=currency,
            store_mov=store_mov
        )

    return StandardPricing(
        shipping_threshold=shipping_threshold,
        shipping_flat=shipping_flat,
        tax_rate=tax_rate,
        currency=currency,
        store_mov=store_mov
    )

def get_pricing_for_user(user: dict[str, Any], config: dict[str, Any] | None) -> PricingStrategy:
    """
    🔥 AMAZON STYLE MAGIC: Read user tier and apply business logic.
    """
    base_strategy = get_pricing_from_config(config)

    user_tier = user.get("tier") if user else "normal"
    
    # If user is a VIP, Premium, or Prime member, wrap their pricing in FreeShipping
    if user_tier in ["premium", "vip", "prime"]:
        return FreeShippingPricing(base_strategy)

    return base_strategy