"""
Pricing Domain Service
======================
Path: app/domains/pricing/service.py

Re-exports the canonical pricing strategies from the legacy services
location. Pricing has no own router, DTOs, or policy — it is a pure
calculation layer used by cart and orders.
"""
from app.services.pricing.service import (
    PriceBreakdown,
    PricingStrategy,
    StandardPricing,
    ZeroTaxPricing,
    FreeShippingPricing,
    get_pricing_from_config,
    get_pricing_for_user,
)

__all__ = [
    "PriceBreakdown",
    "PricingStrategy",
    "StandardPricing",
    "ZeroTaxPricing",
    "FreeShippingPricing",
    "get_pricing_from_config",
    "get_pricing_for_user",
]
