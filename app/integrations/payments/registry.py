"""
Payment Registry
Path: app/integrations/payments/registry.py
"""
from .stripe_impl import StripeProvider

PAYMENT_REGISTRY = {
    "stripe": StripeProvider,
    # "razorpay": RazorpayProvider, (Indian Market expansion future)
}

def get_payment_provider(provider_name: str = "stripe"):
    provider_class = PAYMENT_REGISTRY.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Payment provider '{provider_name}' is not registered.")
    return provider_class()