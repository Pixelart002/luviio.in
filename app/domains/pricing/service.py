"""
Pricing Service — SSOT Architecture (STRICT MODE & ZERO FALLBACKS)
==================================================================
Path: app/domains/pricing/service.py

Pricing is authoritative for checkout totals. Configuration is supplied by
system_settings through the canonical backend configuration path; missing
financial configuration must fail closed rather than silently inventing a
rate.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceBreakdown:
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "subtotal": float(round(self.subtotal, 2)),
            "shipping_cost": float(round(self.shipping, 2)),
            "tax_amount": float(round(self.tax, 2)),
            "total_amount": float(round(self.total, 2)),
            "currency": self.currency,
        }

    @property
    def shipping_is_free(self) -> bool:
        return self.shipping == Decimal("0")


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
    def currency(self) -> str: ...


class StandardPricing(PricingStrategy):
    def __init__(self, shipping_threshold: Decimal, shipping_flat: Decimal, currency: str) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat
        self._currency = currency

    @property
    def shipping_enabled(self) -> bool:
        return self._flat > Decimal("0") or self._threshold > Decimal("0")

    @property
    def shipping_threshold(self) -> Decimal:
        return self._threshold

    @property
    def currency(self) -> str:
        return self._currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        if not items:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart cannot be empty.")

        calc_subtotal = Decimal("0")
        calc_tax = Decimal("0")

        for item in items:
            prod_data = item.get("products") or item
            if "quantity" not in item or item["quantity"] is None:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
            item_qty = Decimal(str(item["quantity"]))
            if item_qty <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid item quantity.")

            if "price_snapshot" in item and item["price_snapshot"] is not None:
                price_val = item["price_snapshot"]
            elif "unit_price" in item and item["unit_price"] is not None:
                price_val = item["unit_price"]
            elif "price" in prod_data and prod_data["price"] is not None:
                price_val = prod_data["price"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")

            item_price = Decimal(str(price_val))
            if item_price < 0:
                raise HTTPException(status_code=500, detail="Invalid product price.")

            if prod_data.get("gst_percentage") is not None:
                item_gst_pct = prod_data["gst_percentage"]
            elif item.get("gst_percentage") is not None:
                item_gst_pct = item["gst_percentage"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")

            item_tax_rate = Decimal(str(item_gst_pct)) / Decimal("100")
            item["price_snapshot"] = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = float(item_gst_pct)

            item_sub = item_price * item_qty
            calc_subtotal += item_sub
            calc_tax += item_sub * item_tax_rate

        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if calc_subtotal >= self._threshold else self._flat
        return PriceBreakdown(
            subtotal=calc_subtotal,
            shipping=shipping,
            tax=calc_tax,
            total=calc_subtotal + shipping + calc_tax,
            currency=self._currency,
        )


class ZeroTaxPricing(PricingStrategy):
    def __init__(self, shipping_threshold: Decimal, shipping_flat: Decimal, currency: str) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat
        self._currency = currency

    @property
    def shipping_enabled(self) -> bool:
        return self._flat > Decimal("0") or self._threshold > Decimal("0")

    @property
    def shipping_threshold(self) -> Decimal:
        return self._threshold

    @property
    def currency(self) -> str:
        return self._currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        if not items:
            raise HTTPException(status_code=400, detail="Cart cannot be empty.")

        calc_subtotal = Decimal("0")
        for item in items:
            prod_data = item.get("products") or item
            if "quantity" not in item or item["quantity"] is None:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
            item_qty = Decimal(str(item["quantity"]))
            if item_qty <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid item quantity.")

            if "price_snapshot" in item and item["price_snapshot"] is not None:
                price_val = item["price_snapshot"]
            elif "unit_price" in item and item["unit_price"] is not None:
                price_val = item["unit_price"]
            elif "price" in prod_data and prod_data["price"] is not None:
                price_val = prod_data["price"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")

            item_price = Decimal(str(price_val))
            if item_price < 0:
                raise HTTPException(status_code=500, detail="Invalid product price.")
            item["price_snapshot"] = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = 0.0
            calc_subtotal += item_price * item_qty

        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if calc_subtotal >= self._threshold else self._flat
        return PriceBreakdown(
            subtotal=calc_subtotal,
            shipping=shipping,
            tax=Decimal("0"),
            total=calc_subtotal + shipping,
            currency=self._currency,
        )


class FreeShippingPricing(PricingStrategy):
    def __init__(self, base_strategy: PricingStrategy) -> None:
        self._base = base_strategy

    @property
    def shipping_enabled(self) -> bool:
        return False

    @property
    def shipping_threshold(self) -> Decimal:
        return self._base.shipping_threshold

    @property
    def currency(self) -> str:
        return self._base.currency

    def calculate(self, items: List[dict[str, Any]]) -> PriceBreakdown:
        original = self._base.calculate(items=items)
        if original.subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), original.currency)
        return PriceBreakdown(
            subtotal=original.subtotal,
            shipping=Decimal("0"),
            tax=original.tax,
            total=original.subtotal + original.tax,
            currency=original.currency,
        )


def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    if not config:
        logger.error("Pricing configuration missing; failing closed.")
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")

    required = ("tax_enabled", "shipping_enabled", "currency", "shipping_flat", "shipping_threshold")
    missing = [key for key in required if key not in config or config[key] is None]
    if missing:
        logger.error("Incomplete pricing configuration; missing keys: %s", missing)
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")

    tax_enabled = config["tax_enabled"]
    shipping_enabled = config["shipping_enabled"]
    currency = str(config["currency"]).strip().upper()
    if not currency:
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")

    try:
        shipping_flat = Decimal(str(config["shipping_flat"]))
        shipping_threshold = Decimal(str(config["shipping_threshold"]))
    except (ArithmeticError, ValueError, TypeError) as exc:
        logger.error("Invalid pricing configuration", exc_info=True)
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.") from exc

    if shipping_flat < 0 or shipping_threshold < 0:
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")

    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
            currency=currency,
        )

    return StandardPricing(
        shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
        shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
        currency=currency,
    )


def get_pricing_for_user(user: dict[str, Any], config: dict[str, Any] | None) -> PricingStrategy:
    from app.domains.subscriptions.tier_registry import get_tier_perks

    base_strategy = get_pricing_from_config(config)
    user_tier = user.get("tier") if user else "free"
    perks = get_tier_perks(user_tier)
    if perks.free_shipping:
        return FreeShippingPricing(base_strategy)
    return base_strategy
