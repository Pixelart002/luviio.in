"""Pricing Service — SSOT Architecture (STRICT MODE & ZERO FALLBACKS)."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, List

from fastapi import HTTPException, status

from app.domains.shipping.calculator import calculate_settings_shipping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PriceBreakdown:
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    shipping_tax: Decimal = Decimal("0.00")

    def as_dict(self) -> dict[str, Any]:
        return {
            "subtotal": float(round(self.subtotal, 2)),
            "shipping_cost": float(round(self.shipping, 2)),
            "shipping_tax_amount": float(round(self.shipping_tax, 2)),
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


def _validated_quantity(item: dict[str, Any]) -> Decimal:
    if "quantity" not in item or item["quantity"] is None:
        raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
    try:
        quantity = Decimal(str(item["quantity"]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid item quantity.") from exc
    if not quantity.is_finite() or quantity <= 0 or quantity != quantity.to_integral_value():
        raise HTTPException(status_code=422, detail="Invalid item quantity.")
    return quantity


def _validated_price(value: Any) -> Decimal:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Invalid product price.") from exc
    if not price.is_finite() or price < 0:
        raise HTTPException(status_code=500, detail="Invalid product price.")
    return price


def _validated_gst(value: Any) -> Decimal:
    try:
        gst = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Invalid GST configuration.") from exc
    if not gst.is_finite() or gst < 0 or gst > 100:
        raise HTTPException(status_code=500, detail="Invalid GST configuration.")
    return gst


def _shipping_tax(items: List[dict[str, Any]], shipping: Decimal, subtotal: Decimal) -> Decimal:
    """Allocate charged freight across taxable lines and apply each line's GST rate.

    CGST Act section 15(2)(c) includes incidental expenses charged in
    connection with a supply. CBIC also treats ancillary transport/cartage as
    part of a composite supply when supplied with the goods. Allocation by
    taxable line value keeps mixed-GST carts auditable.
    """
    if shipping <= 0 or subtotal <= 0:
        return Decimal("0.00")

    tax = Decimal("0")
    for item in items:
        prod_data = item.get("products") or item
        qty = _validated_quantity(item)
        price = _validated_price(
            item.get("price_snapshot")
            if item.get("price_snapshot") is not None
            else item.get("unit_price")
            if item.get("unit_price") is not None
            else prod_data.get("price")
        )
        gst_value = prod_data.get("gst_percentage")
        if gst_value is None:
            gst_value = item.get("gst_percentage")
        gst = _validated_gst(gst_value)
        line_value = price * qty
        allocated_shipping = shipping * line_value / subtotal
        tax += allocated_shipping * gst / Decimal("100")

    return tax.quantize(Decimal("0.01"))


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
        product_tax = Decimal("0")
        for item in items:
            prod_data = item.get("products") or item
            item_qty = _validated_quantity(item)
            if item.get("price_snapshot") is not None:
                price_val = item["price_snapshot"]
            elif item.get("unit_price") is not None:
                price_val = item["unit_price"]
            elif prod_data.get("price") is not None:
                price_val = prod_data["price"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
            item_price = _validated_price(price_val)
            if prod_data.get("gst_percentage") is not None:
                item_gst_pct = prod_data["gst_percentage"]
            elif item.get("gst_percentage") is not None:
                item_gst_pct = item["gst_percentage"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
            gst_percentage = _validated_gst(item_gst_pct)
            item["price_snapshot"] = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = float(gst_percentage)
            item_sub = item_price * item_qty
            calc_subtotal += item_sub
            product_tax += item_sub * (gst_percentage / Decimal("100"))
        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)
        shipping = calculate_settings_shipping(
            subtotal=calc_subtotal,
            shipping_enabled=self.shipping_enabled,
            threshold=self._threshold,
            flat_rate=self._flat,
        )
        shipping_tax = _shipping_tax(items, shipping, calc_subtotal)
        total_tax = product_tax + shipping_tax
        return PriceBreakdown(
            subtotal=calc_subtotal,
            shipping=shipping,
            tax=total_tax,
            total=calc_subtotal + shipping + total_tax,
            currency=self._currency,
            shipping_tax=shipping_tax,
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
            item_qty = _validated_quantity(item)
            if item.get("price_snapshot") is not None:
                price_val = item["price_snapshot"]
            elif item.get("unit_price") is not None:
                price_val = item["unit_price"]
            elif prod_data.get("price") is not None:
                price_val = prod_data["price"]
            else:
                raise HTTPException(status_code=500, detail="Pricing data is incomplete.")
            item_price = _validated_price(price_val)
            item["price_snapshot"] = float(round(item_price, 2))
            item["gst_percentage_snapshot"] = 0.0
            calc_subtotal += item_price * item_qty
        if calc_subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)
        shipping = calculate_settings_shipping(
            subtotal=calc_subtotal,
            shipping_enabled=self.shipping_enabled,
            threshold=self._threshold,
            flat_rate=self._flat,
        )
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
            shipping_tax=Decimal("0"),
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
    except (ArithmeticError, ValueError, TypeError, InvalidOperation) as exc:
        logger.error("Invalid pricing configuration", exc_info=True)
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.") from exc
    if not shipping_flat.is_finite() or not shipping_threshold.is_finite() or shipping_flat < 0 or shipping_threshold < 0:
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")
    if not isinstance(tax_enabled, bool) or not isinstance(shipping_enabled, bool):
        raise HTTPException(status_code=503, detail="Pricing service temporarily unavailable. Please try again.")
    if currency != "INR":
        logger.error("Unsupported checkout currency: %s", currency)
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
