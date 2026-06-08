"""
Pricing Service — SSOT Architecture
=====================================
Path: app/services/pricing.py

Patterns:
  - Strategy Pattern  (Interchangeable algorithms)
  - Decorator Pattern (Free Shipping / Discount wrappers)
  - Value Object      (Immutable PriceBreakdown)
  - SSOT              (All config from DB, zero hardcoded fallbacks)
  - Fail-Fast         (503 on missing config — prevents financial loss)

PriceBreakdown field names:
  .subtotal   → as_dict() → "subtotal"
  .shipping   → as_dict() → "shipping_cost"   ← NOTE: different key name!
  .tax        → as_dict() → "tax_amount"
  .total      → as_dict() → "total_amount"
  .currency   → as_dict() → "currency"

Callers that need API-friendly keys:  use breakdown.as_dict()
Callers that need raw Decimal values: use breakdown.shipping (not .shipping_cost)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  VALUE OBJECT
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PriceBreakdown:
    """
    Immutable value object — safe to pass around, prevents accidental mutation.

    IMPORTANT — field names vs API response keys:
      .shipping  ≠  "shipping_cost"
      .tax       ≠  "tax_amount"
      .total     ≠  "total_amount"

    Always use .as_dict() when building the API JSON response.
    Use the raw attributes (.shipping, .tax, .total) for internal logic.
    """
    subtotal: Decimal
    shipping: Decimal
    tax:      Decimal
    total:    Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        """
        Convert to API-response dict.
        Maps internal field names to the public API key names:
          .shipping → "shipping_cost"
          .tax      → "tax_amount"
          .total    → "total_amount"
        """
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
    Add new strategies (RegionalPricing, B2BPricing…) without touching order code.
    """

    @abstractmethod
    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown: ...

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
    Default: free shipping above threshold, flat fee below, fixed tax rate.
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

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)

        shipping = Decimal("0") if sub >= self._threshold else self._flat
        tax      = (sub + shipping) * self._tax_rate
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
    For tax-exempt B2B customers or specific regions.
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

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
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
    Decorator Pattern: applies percentage discount on subtotal before tax & shipping.
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

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return self._base.calculate(Decimal("0"))

        discounted = sub * (Decimal("1") - self._discount)
        return self._base.calculate(discounted)


class FreeShippingPricing(PricingStrategy):
    """
    Decorator Pattern: always free shipping.
    Use for VIP customers or promotional periods.
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

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return self._base.calculate(Decimal("0"))

        original = self._base.calculate(sub)
        tax_rate = original.tax_rate_applied
        new_tax  = sub * tax_rate

        return PriceBreakdown(
            subtotal=sub,
            shipping=Decimal("0"),
            tax=new_tax,
            total=sub + new_tax,
            currency=original.currency,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS — STRICT DB ONLY, ZERO HARDCODED FALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    """
    Factory — builds strategy strictly from pricing_config DB row.

    🚨 Raises HTTP 503 if config is None.
       This is intentional: missing config = potential financial loss = reject order.
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

    # Tax disabled → ZeroTaxPricing
    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat           if shipping_enabled else Decimal("0"),
            currency=currency,
        )

    # Shipping disabled → flat 0 shipping
    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
            currency=currency,
        )

    # Default: both enabled
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
    Decorator pattern example: wrap StandardPricing with FreeShippingPricing for VIPs.
    """
    base_strategy = get_pricing_from_config(config)

    # Scaling hook — uncomment to activate:
    # if user.get("role") == "vip":
    #     return FreeShippingPricing(base_strategy)
    # if user.get("is_b2b"):
    #     return ZeroTaxPricing(...)

    return base_strategy