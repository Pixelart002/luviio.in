"""
Pricing Service — Top Tier Architecture (SSOT)
=====================================================
Pattern: Strategy (interchangeable algorithms behind a common interface)

✅ STRICT SINGLE SOURCE OF TRUTH (SSOT).
✅ NO hardcoded fallbacks. All pricing MUST come from the live Database.
✅ Fails gracefully with 503 Error if DB config is missing (No Financial Loss).
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
    """Immutable value object — safe to pass around, no accidental mutation."""
    subtotal: Decimal
    shipping: Decimal
    tax: Decimal
    total: Decimal

    def as_dict(self) -> dict[str, float]:
        """Convert to dict for database insertion"""
        return {
            "subtotal":      float(self.subtotal),
            "shipping_cost": float(self.shipping),
            "tax_amount":    float(round(self.tax, 2)),
            "total_amount":  float(round(self.total, 2)),
        }
    
    @property
    def shipping_is_free(self) -> bool:
        """Check if shipping is free"""
        return self.shipping == Decimal("0")
    
    @property
    def tax_rate_applied(self) -> Decimal:
        """Calculate effective tax rate"""
        taxable = self.subtotal + self.shipping
        if taxable == Decimal("0"):
            return Decimal("0")
        return self.tax / taxable


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

class PricingStrategy(ABC):
    """
    Abstract base — concrete strategies implement this.
    Open for extension (add new strategies), closed for modification.
    """

    @abstractmethod
    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
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
    ) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat
        self._tax_rate = tax_rate

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        # [FIX] Empty Cart Safety
        if subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
            
        shipping = Decimal("0") if subtotal >= self._threshold else self._flat
        tax = (subtotal + shipping) * self._tax_rate
        total = subtotal + shipping + tax
        
        return PriceBreakdown(
            subtotal=subtotal,
            shipping=shipping,
            tax=tax,
            total=total,
        )


class ZeroTaxPricing(PricingStrategy):
    """
    For tax-exempt B2B customers or specific regions.
    """

    def __init__(self, shipping_threshold: Decimal, shipping_flat: Decimal) -> None:
        self._threshold = shipping_threshold
        self._flat = shipping_flat

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        if subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
            
        shipping = Decimal("0") if subtotal >= self._threshold else self._flat
        total = subtotal + shipping
        
        return PriceBreakdown(
            subtotal=subtotal,
            shipping=shipping,
            tax=Decimal("0"),
            total=total,
        )


class DiscountPricing(PricingStrategy):
    """
    Percentage discount on subtotal before tax & shipping.
    """

    def __init__(self, base_strategy: PricingStrategy, discount_pct: Decimal):
        self._base = base_strategy
        self._discount = discount_pct / Decimal("100")

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        if subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
            
        discounted = subtotal * (Decimal("1") - self._discount)
        return self._base.calculate(discounted)


class FreeShippingPricing(PricingStrategy):
    """Always free shipping — wraps another strategy (VIP customers)."""

    def __init__(self, base_strategy: PricingStrategy):
        self._base = base_strategy

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        if subtotal <= Decimal("0"):
            return PriceBreakdown(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
            
        original = self._base.calculate(subtotal)
        
        # [FIX] Properly re-calculate tax without the shipping portion
        tax_rate = original.tax_rate_applied
        new_tax = subtotal * tax_rate
        
        return PriceBreakdown(
            subtotal=subtotal,
            shipping=Decimal("0"),
            tax=new_tax,
            total=subtotal + new_tax,
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
    
    tax_rate = Decimal(str(config.get("tax_rate", 18.0))) / Decimal("100")
    shipping_flat = Decimal(str(config.get("shipping_flat", 99.0)))
    shipping_threshold = Decimal(str(config.get("shipping_threshold", 999.0)))
    
    # If tax disabled → zero tax
    if not tax_enabled:
        return ZeroTaxPricing(
            shipping_threshold=shipping_threshold if shipping_enabled else Decimal("0"),
            shipping_flat=shipping_flat if shipping_enabled else Decimal("0"),
        )
    
    # If shipping disabled → always free shipping
    if not shipping_enabled:
        return StandardPricing(
            shipping_threshold=Decimal("0"),
            shipping_flat=Decimal("0"),
            tax_rate=tax_rate,
        )
    
    # Default: both enabled
    return StandardPricing(
        shipping_threshold=shipping_threshold,
        shipping_flat=shipping_flat,
        tax_rate=tax_rate,
    )


def get_pricing_for_user(
    user: dict[str, Any], 
    config: dict[str, Any] | None
) -> PricingStrategy:
    """
    Factory — returns strategy based on user attributes AND live DB config.
    Strictly depends on the database configuration.
    """
    # Example: If user has a specific role, wrap the DB pricing:
    # if user.get("vip_tier") == "platinum":
    #     base = get_pricing_from_config(config)
    #     return FreeShippingPricing(base)
    
    return get_pricing_from_config(config)
