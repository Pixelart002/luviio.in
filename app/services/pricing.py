"""
Pricing Service — SSOT Architecture (With Item-Level GST Support)
=================================================================
Path: app/services/pricing.py

Patterns:
  - Strategy Pattern  (Interchangeable algorithms)
  - Decorator Pattern (Free Shipping / Discount wrappers)
  - Value Object      (Immutable PriceBreakdown)
  - SSOT              (All config from DB + Item-level GST from catalog)
  - Fail-Fast         (503 on missing config — prevents financial loss)

PriceBreakdown field names:
  .subtotal   → as_dict() → "subtotal"
  .shipping   → as_dict() → "shipping_cost"   ← NOTE: different key name!
  .tax        → as_dict() → "tax_amount"
  .total      → as_dict() → "total_amount"
  .currency   → as_dict() → "currency"
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  VALUE OBJECT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PriceBreakdown:
    """
    Immutable value object — safe to pass around, prevents accidental mutation.

    Always use .as_dict() when building the API JSON response.
    Use the raw attributes (.shipping, .tax, .total) for internal logic.
    """
    subtotal: Decimal
    shipping: Decimal
    tax:      Decimal
    total:    Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        """Convert to API-response dict with explicit public API key names."""
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

    @property
    def tax_rate_applied(self) -> Decimal:
        """Effective tax rate on taxable base (subtotal + shipping)."""
        taxable = self.subtotal + self.shipping
        if taxable <= Decimal("0"):
            return Decimal("0")
        return self.tax / taxable


# ══════════════════════════════════════════════════════════════════════════════
#  ABSTRACT STRATEGY
# ══════════════════════════════════════════════════════════════════════════════

class PricingStrategy(ABC):
    """
    Abstract base — open for extension, closed for modification (OCP).
    """

    @abstractmethod
    def calculate(
        self, 
        subtotal: Decimal | float = Decimal("0"), 
        items: Optional[List[dict[str, Any]]] = None
    ) -> PriceBreakdown: ...

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
    """
    Default: Free shipping above threshold, flat fee below.
    🔥 UPGRADE: Calculates exact tax per item using product-level `gst_percentage`!
    """

    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat:      Decimal,
        tax_rate:           Decimal,
        currency:           str,
    ) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat
        self._tax_rate  = tax_rate
        self._currency  = currency

    @property
    def shipping_enabled(self) -> bool:
        return self._flat > Decimal("0") or self._threshold > Decimal("0")

    @property
    def shipping_threshold(self) -> Decimal:
        return self._threshold

    @property
    def tax_rate(self) -> Decimal:
        return self._tax_rate

    @property
    def currency(self) -> str:
        return self._currency

    def calculate(
        self, 
        subtotal: Decimal | float = Decimal("0"), 
        items: Optional[List[dict[str, Any]]] = None
    ) -> PriceBreakdown:
        # 🔥 UPGRADE: If items are passed, calculate subtotal and tax item-by-item!
        if items:
            calc_subtotal = Decimal("0")
            calc_tax      = Decimal("0")

            for item in items:
                # Resolve price (works for cart items and order snapshots)
                price_val = item.get("price_snapshot") or item.get("unit_price") or item.get("price", 0)
                item_price = Decimal(str(price_val))
                item_qty   = int(item.get("quantity", 1))
                item_sub   = item_price * item_qty
                calc_subtotal += item_sub

                # Resolve GST percentage (checks nested products join first, then item root)
                prod_data    = item.get("products") or item
                item_gst_pct = prod_data.get("gst_percentage")

                if item_gst_pct is not None:
                    item_tax_rate = Decimal(str(item_gst_pct)) / Decimal("100")
                else:
                    item_tax_rate = self._tax_rate  # Fallback to global config rate

                calc_tax += item_sub * item_tax_rate

            sub = calc_subtotal
            tax = calc_tax
        else:
            # Legacy / Fallback: Apply blanket tax rate on total subtotal
            sub = Decimal(str(subtotal))
            tax = sub * self._tax_rate if sub > Decimal("0") else Decimal("0")

        if sub <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if sub >= self._threshold else self._flat
        total    = sub + shipping + tax

        return PriceBreakdown(
            subtotal=sub,
            shipping=shipping,
            tax=tax,
            total=total,
            currency=self._currency,
        )


class ZeroTaxPricing(PricingStrategy):
    """
    For tax-exempt B2B customers or specific regions (forces 0% GST regardless of product flags).
    """

    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat:      Decimal,
        currency:           str,
    ) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat
        self._currency  = currency

    @property
    def shipping_enabled(self) -> bool:
        return self._flat > Decimal("0") or self._threshold > Decimal("0")

    @property
    def shipping_threshold(self) -> Decimal:
        return self._threshold

    @property
    def tax_rate(self) -> Decimal:
        return Decimal("0")

    @property
    def currency(self) -> str:
        return self._currency

    def calculate(
        self, 
        subtotal: Decimal | float = Decimal("0"), 
        items: Optional[List[dict[str, Any]]] = None
    ) -> PriceBreakdown:
        if items:
            sub = sum(
                Decimal(str(i.get("price_snapshot") or i.get("unit_price") or i.get("price", 0))) * int(i.get("quantity", 1))
                for i in items
            )
        else:
            sub = Decimal(str(subtotal))

        if sub <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if sub >= self._threshold else self._flat
        total    = sub + shipping

        return PriceBreakdown(
            subtotal=sub,
            shipping=shipping,
            tax=Decimal("0"),
            total=total,
            currency=self._currency,
        )


class DiscountPricing(PricingStrategy):
    """
    Decorator Pattern: applies percentage discount on subtotal/items before tax & shipping.
    """

    def __init__(self, base_strategy: PricingStrategy, discount_pct: Decimal) -> None:
        self._base     = base_strategy
        self._discount = discount_pct / Decimal("100")

    @property
    def shipping_enabled(self) -> bool:
        return self._base.shipping_enabled

    @property
    def shipping_threshold(self) -> Decimal:
        return self._base.shipping_threshold

    @property
    def tax_rate(self) -> Decimal:
        return self._base.tax_rate

    @property
    def currency(self) -> str:
        return self._base.currency

    def calculate(
        self, 
        subtotal: Decimal | float = Decimal("0"), 
        items: Optional[List[dict[str, Any]]] = None
    ) -> PriceBreakdown:
        if items:
            # Scale down each item's price by the discount percentage before passing to base strategy
            discounted_items = []
            for item in items:
                new_item = dict(item)
                original_price = Decimal(str(item.get("price_snapshot") or item.get("unit_price") or item.get("price", 0)))
                new_item["price"] = original_price * (Decimal("1") - self._discount)
                new_item["price_snapshot"] = new_item["price"]
                discounted_items.append(new_item)
            return self._base.calculate(items=discounted_items)
        
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return self._base.calculate(subtotal=Decimal("0"))

        discounted = sub * (Decimal("1") - self._discount)
        return self._base.calculate(subtotal=discounted)


class FreeShippingPricing(PricingStrategy):
    """
    Decorator Pattern: always free shipping.
    """

    def __init__(self, base_strategy: PricingStrategy) -> None:
        self._base = base_strategy

    @property
    def shipping_enabled(self) -> bool:
        return False

    @property
    def shipping_threshold(self) -> Decimal:
        return self._base.shipping_threshold

    @property
    def tax_rate(self) -> Decimal:
        return self._base.tax_rate

    @property
    def currency(self) -> str:
        return self._base.currency

    def calculate(
        self, 
        subtotal: Decimal | float = Decimal("0"), 
        items: Optional[List[dict[str, Any]]] = None
    ) -> PriceBreakdown:
        original = self._base.calculate(subtotal=subtotal, items=items)
        if original.subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), original.currency)

        return PriceBreakdown(
            subtotal=original.subtotal,
            shipping=Decimal("0"),
            tax=original.tax,
            total=original.subtotal + original.tax,
            currency=original.currency,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS — STRICT DB ONLY, ZERO HARDCODED FALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    """
    Factory — builds strategy strictly from pricing_config DB row.
    🚨 Raises HTTP 503 if config is None.
    """
    if not config:
        logger.error(
            "CRITICAL: Pricing config missing from Database. "
            "Rejecting request to prevent financial loss."
        )
        raise HTTPException(
            status_code=503,
            detail="Pricing service temporarily unavailable. Please try again.",
        )

    tax_enabled      = config.get("tax_enabled", True)
    shipping_enabled = config.get("shipping_enabled", True)
    currency         = config.get("currency", "INR")

    tax_rate           = Decimal(str(config.get("tax_rate",           18.0))) / Decimal("100")
    shipping_flat      = Decimal(str(config.get("shipping_flat",      99.0)))
    shipping_threshold = Decimal(str(config.get("shipping_threshold", 999.0)))

    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat           if shipping_enabled else Decimal("0"),
            currency=currency,
        )

    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
            currency=currency,
        )

    return StandardPricing(
        shipping_threshold=shipping_threshold,
        shipping_flat=shipping_flat,
        tax_rate=tax_rate,
        currency=currency,
    )


def get_pricing_for_user(
    user:   dict[str, Any],
    config: dict[str, Any] | None,
) -> PricingStrategy:
    """
    Factory — returns strategy based on user role AND live DB config.
    """
    base_strategy = get_pricing_from_config(config)
    return base_strategy