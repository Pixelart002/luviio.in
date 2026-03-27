"""
Pricing Service — Strategy Pattern
====================================
Pattern: Strategy (interchangeable algorithms behind a common interface)
Why: Pricing rules change (promotions, regions, B2B) — open for extension,
     closed for modification (Open/Closed Principle).

LLD concepts applied:
  Strategy Pattern    → swap pricing logic without changing order code
  Single Responsibility → pricing is its own concern, not inside the order router
  Dependency Inversion  → OrderService depends on PricingStrategy abstraction
  Designing for Testability → each strategy is unit-testable in isolation
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PriceBreakdown:
    """Immutable value object — safe to pass around, no accidental mutation."""
    subtotal:  Decimal
    shipping:  Decimal
    tax:       Decimal
    total:     Decimal

    def as_dict(self) -> dict[str, float]:
        return {
            "subtotal":      float(self.subtotal),
            "shipping_cost": float(self.shipping),
            "tax_amount":    float(self.tax.quantize(Decimal("0.01"))),
            "total_amount":  float(self.total.quantize(Decimal("0.01"))),
        }


class PricingStrategy(ABC):
    """Abstract base — concrete strategies implement this."""

    @abstractmethod
    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        ...


class StandardPricing(PricingStrategy):
    """
    Default: free shipping above threshold, flat fee below, fixed tax rate.
    Replace with RegionalPricing / SubscriberPricing etc. without touching order code.
    """

    def __init__(
        self,
        shipping_threshold: Decimal,
        shipping_flat: Decimal,
        tax_rate: Decimal,
    ) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat
        self._tax_rate  = tax_rate

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        shipping = Decimal("0") if subtotal >= self._threshold else self._flat
        tax      = (subtotal + shipping) * self._tax_rate
        total    = subtotal + shipping + tax
        return PriceBreakdown(
            subtotal=subtotal,
            shipping=shipping,
            tax=tax,
            total=total,
        )


class ZeroTaxPricing(PricingStrategy):
    """For tax-exempt B2B customers or specific regions — swap in without touching orders."""

    def __init__(self, shipping_threshold: Decimal, shipping_flat: Decimal) -> None:
        self._threshold = shipping_threshold
        self._flat      = shipping_flat

    def calculate(self, subtotal: Decimal) -> PriceBreakdown:
        shipping = Decimal("0") if subtotal >= self._threshold else self._flat
        total    = subtotal + shipping
        return PriceBreakdown(
            subtotal=subtotal, 
            shipping=shipping, 
            tax=Decimal("0"), 
            total=total
        )


def get_default_pricing() -> PricingStrategy:
    """
    Factory function — returns the configured strategy.
    Swap implementation here without changing any router code.
    """
    from app.config import settings
    return StandardPricing(
        shipping_threshold=settings.SHIPPING_THRESHOLD,
        shipping_flat=settings.SHIPPING_FLAT,
        tax_rate=settings.TAX_RATE,
    )