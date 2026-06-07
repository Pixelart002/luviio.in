"""
Stripe Implementation
Path: app/integrations/payments/stripe_impl.py
"""
import stripe
import logging
from app.core.config import settings
from .base import PaymentProvider

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeProvider(PaymentProvider):
    def create_payment_intent(self, amount: float, currency: str, order_id: str) -> dict:
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(amount * 100), # Stripe uses smallest currency unit (paise/cents)
                currency=currency.lower(),
                metadata={"order_id": order_id}
            )
            return {"client_secret": intent.client_secret, "id": intent.id}
        except Exception as e:
            logger.error("Stripe Intent creation failed: %s", e)
            raise

    def process_refund(self, payment_intent_id: str) -> bool:
        try:
            stripe.Refund.create(payment_intent=payment_intent_id)
            logger.info("Stripe Refund successful for intent: %s", payment_intent_id)
            return True
        except Exception as e:
            logger.error("Stripe Refund failed: %s", e)
            raise