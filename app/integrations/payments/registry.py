"""
Payment Registry
================
Path: app/integrations/payments/registry.py
"""
from typing import Dict, Type
from app.integrations.payments.base import PaymentProvider
from app.integrations.payments.stripe_impl import StripeProvider

PAYMENT_REGISTRY: Dict[str, Type[PaymentProvider]] = {
    "stripe": StripeProvider,
}

def get_payment_provider(provider_name: str = "stripe") -> PaymentProvider:
    provider_class = PAYMENT_REGISTRY.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Payment provider '{provider_name}' is not registered.")
    return provider_class()