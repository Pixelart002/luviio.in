"""
Compatibility shim for the retired pricing service path.

Canonical ownership: app.domains.pricing.service
Do not add business logic here.
"""

from app.domains.pricing.service import (  # noqa: F401
    PriceBreakdown,
    PricingStrategy,
    StandardPricing,
    get_pricing_from_config,
)

__all__ = [
    "PriceBreakdown",
    "PricingStrategy",
    "StandardPricing",
    "get_pricing_from_config",
]
