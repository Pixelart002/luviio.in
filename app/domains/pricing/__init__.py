"""
Pricing Domain
==============
Path: app/domains/pricing/__init__.py

Owns pricing strategy selection: standard, zero-tax, and free-shipping
calculations used by cart and orders.
"""
from app.domains.pricing.service import (
    FreeShippingPricing,
    PriceBreakdown,
    PricingStrategy,
    StandardPricing,
    ZeroTaxPricing,
    get_pricing_for_user,
    get_pricing_from_config,
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
