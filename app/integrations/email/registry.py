"""
Email Registry (Factory Pattern)
Path: app/integrations/email/registry.py
"""
import logging
from .resend_impl import (
    send_welcome_email, 
    send_order_confirmation, 
    send_order_shipped, 
    send_cart_reminder_email, 
    send_payment_success
)

logger = logging.getLogger(__name__)

class ResendAdapter:
    """Adapts the functional Resend implementation to our Async Interface"""
    async def send_welcome_email(self, to: str, name: str) -> None:
        await send_welcome_email(to, name)
        
    async def send_order_confirmation(self, to: str, order: dict) -> None:
        await send_order_confirmation(to, order)
        
    async def send_order_shipped(self, to: str, order: dict, tracking_number: str) -> None:
        await send_order_shipped(to, order, tracking_number)
        
    async def send_cart_reminder_email(self, to: str, name: str, items: list) -> None:
        await send_cart_reminder_email(to, name, items)

    async def send_payment_success(self, to: str, order: dict) -> None:
        await send_payment_success(to, order)

# The Registry Dictionary
EMAIL_REGISTRY = {
    "resend": ResendAdapter,
    # "aws_ses": AWSSESAdapter, (Future scaling)
}

def get_email_provider(provider_name: str = "resend"):
    """Returns the requested email client dynamically."""
    provider_class = EMAIL_REGISTRY.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Email provider '{provider_name}' is not registered.")
    return provider_class()