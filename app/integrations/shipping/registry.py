"""Shipping provider registry."""
from __future__ import annotations

from app.integrations.shipping.base import ShippingProvider
from app.integrations.shipping.shiprocket import ShiprocketProvider

SHIPPING_PROVIDER_REGISTRY: dict[str, type[ShippingProvider]] = {
    "shiprocket": ShiprocketProvider,
}


def get_shipping_provider(key: str = "shiprocket") -> ShippingProvider:
    normalized = (key or "shiprocket").strip().lower()
    provider_cls = SHIPPING_PROVIDER_REGISTRY.get(normalized)
    if not provider_cls:
        raise ValueError(f"Unsupported shipping provider: {normalized}")
    return provider_cls()
