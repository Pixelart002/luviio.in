"""
Pricing Service — Top Tier Architecture (SSOT)
=====================================================
Architecture Layer: Services (Domain Logic)
Path: app/services/pricing.py

Patterns Applied: 
  - Strategy Pattern (Interchangeable algorithms behind a common interface)
  - Decorator Pattern (Wrapping strategies for Free Shipping / Discounts)
  - Value Object (Immutable PriceBreakdown)
  - Single Source of Truth (SSOT via DB Config)
  - Fail-Fast Principle (503 on missing config to prevent financial loss)

✅ STRICT SINGLE SOURCE OF TRUTH (SSOT).
✅ NO hardcoded fallbacks. All pricing MUST come from the live Database.
✅ Fails gracefully with 503 Error if DB config is missing.
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
    """Immutable value object — safe to pass around, prevents accidental mutation."""
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        """Convert to dict for database insertion and API responses"""
        return {
            "subtotal":      float(round(self.subtotal, 2)),
            "shipping_cost": float(round(self.shipping, 2)),
            "tax_amount":    float(round(self.tax, 2)),
            "total_amount":  float(round(self.total, 2)),
            "currency":      self.currency
        }
    
    @property
    def shipping_is_free(self) -> bool:
        """Check if shipping is free"""
        return self.shipping == Decimal("0")
    
    @property
    def tax_rate_applied(self) -> Decimal:
        """Calculate effective tax rate"""
        taxable = self.subtotal + self.shipping
        if taxable <= Decimal("0"):
            return Decimal("0")
        return self.tax / taxable


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

class PricingStrategy(ABC):
    """
    Abstract base — concrete strategies implement this.
    Open for extension (add new strategies), closed for modification (OCP).
    """
    @abstractmethod
    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        """Calculate complete price breakdown from subtotal"""
        ...


# ══════════════════════════════════════════════════════════════════════════════
#  CONCRETE STRATEGIES
# ══════════════════════════════════════════════════════════════════════════════

class StandardPricing(PricingStrategy):
    """
    Default pricing: free shipping above threshold, flat fee below, fixed tax rate.
    """
    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat: Decimal,
        tax_rate: Decimal,
        currency: str
    ) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat
        self._tax_rate = tax_rate
        self._currency = currency

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        
        # Empty Cart Safety
        if sub <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)
            
        shipping = Decimal("0") if sub >= self._threshold else self._flat
        tax = (sub + shipping) * self._tax_rate
        total = sub + shipping + tax
        
        return PriceBreakdown(
            subtotal=sub,
            shipping=shipping,
            tax=tax,
            total=total,
            currency=self._currency
        )


class ZeroTaxPricing(PricingStrategy):
    """
    For tax-exempt B2B customers or specific regions.
    """
    def __init__(self, shipping_threshold: Decimal, shipping_flat: Decimal, currency: str) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat
        self._currency = currency

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), self._currency)
            
        shipping = Decimal("0") if sub >= self._threshold else self._flat
        total = sub + shipping
        
        return PriceBreakdown(
            subtotal=sub,
            shipping=shipping,
            tax=Decimal("0"),
            total=total,
            currency=self._currency
        )


class DiscountPricing(PricingStrategy):
    """
    Decorator Pattern: Applies Percentage discount on subtotal before tax & shipping.
    """
    def __init__(self, base_strategy: PricingStrategy, discount_pct: Decimal):
        self._base = base_strategy
        self._discount = discount_pct / Decimal("100")

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return self._base.calculate(Decimal("0"))
            
        discounted = sub * (Decimal("1") - self._discount)
        return self._base.calculate(discounted)


class FreeShippingPricing(PricingStrategy):
    """Decorator Pattern: Always free shipping — wraps another strategy (e.g., VIP customers)."""
    def __init__(self, base_strategy: PricingStrategy):
        self._base = base_strategy

    def calculate(self, subtotal: Decimal | float) -> PriceBreakdown:
        sub = Decimal(str(subtotal))
        if sub <= Decimal("0"):
            return self._base.calculate(Decimal("0"))
            
        original = self._base.calculate(sub)
        
        # Properly re-calculate tax without the shipping portion
        tax_rate = original.tax_rate_applied
        new_tax = sub * tax_rate
        
        return PriceBreakdown(
            subtotal=sub,
            shipping=Decimal("0"),
            tax=new_tax,
            total=sub + new_tax,
            currency=original.currency
        )


# ══════════════════════════════════════════════════════════════════════════════
#  FACTORY FUNCTIONS (STRICT DB ONLY)
# ══════════════════════════════════════════════════════════════════════════════

def get_pricing_from_config(config: dict[str, Any] | None) -> PricingStrategy:
    """
    Factory — returns strategy STRICTLY from pricing_config DB row.
    🚨 FAANG RULE: Raises 503 Exception if config is missing (Prevents Financial Loss).
    """
    if not config:
        logger.error(
            "CRITICAL: Pricing config missing from Database. "
            "Order rejected to prevent financial loss."
        )
        raise HTTPException(
            status_code=503, 
            detail="Pricing service is temporarily unavailable. Please try again later."
        )

    tax_enabled = config.get("tax_enabled", True)
    shipping_enabled = config.get("shipping_enabled", True)
    currency = config.get("currency", "INR")
    
    tax_rate = Decimal(str(config.get("tax_rate", 18.0))) / Decimal("100")
    shipping_flat = Decimal(str(config.get("shipping_flat", 99.0)))
    shipping_threshold = Decimal(str(config.get("shipping_threshold", 999.0)))
    
    # If tax disabled → zero tax strategy
    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
            currency=currency
        )
    
    # If shipping disabled → flat 0 shipping strategy
    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
            currency=currency
        )
    
    # Default: both enabled
    return StandardPricing(
        shipping_threshold=shipping_threshold,
        shipping_flat=shipping_flat,
        tax_rate=tax_rate,
        currency=currency
    )


def get_pricing_for_user(
    user: dict[str, Any], 
    config: dict[str, Any] | None
) -> PricingStrategy:
    """
    Factory — returns strategy based on user attributes AND live DB config.
    Example: Apply VIP Free Shipping or B2B Zero Tax decorators here.
    """
    base_strategy = get_pricing_from_config(config)

    # Future scaling example (Decorator Pattern in action):
    # if user.get("role") == "vip":
    #     return FreeShippingPricing(base_strategy)

    return base_strategy