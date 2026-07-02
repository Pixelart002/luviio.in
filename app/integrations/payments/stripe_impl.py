"""
Stripe Implementation
Path: app/integrations/payments/stripe_impl.py
"""
import logging
import stripe
from app.core.config import settings

logger = logging.getLogger(__name__)

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


class StripeProvider:
    def create_payment_intent(
        self,
        amount_paise: int,
        currency: str,
        order_id: str,
        user_id: str,
        idem_key: str,
    ) -> dict:
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_paise,
                currency=currency.lower(),
                metadata={
                    "order_id": order_id,
                    "user_id": user_id,
                },
                automatic_payment_methods={"enabled": True},
                description=f"{settings.APP_NAME} — Order #{order_id[:8].upper()}",
                idempotency_key=idem_key,
            )

            client_secret = (
                intent.get("client_secret")
                if isinstance(intent, dict)
                else getattr(intent, "client_secret", None)
            )

            if not client_secret:
                raise RuntimeError(
                    "Stripe did not return a client_secret for the new PaymentIntent"
                )

            return {
                "client_secret": client_secret,
                "id": intent.id,
                "status": intent.status,
            }

        except stripe.error.StripeError as e:
            logger.error("Stripe Intent creation failed: %s", e)
            raise

    # 🔥 FIX: Added update_intent_metadata just in case the router is still trying to call it.
    def update_intent_metadata(self, intent_id: str, metadata: dict) -> dict:
        try:
            intent = stripe.PaymentIntent.modify(
                intent_id,
                metadata=metadata,
            )

            return {
                "id": intent.id,
                "status": intent.status,
            }

        except stripe.error.StripeError as e:
            logger.error("Stripe Intent modify failed: %s", e)
            raise

    def retrieve_intent(self, payment_intent_id: str) -> dict:
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)

            # Return full metadata in the retrieve response
            return {
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
                "metadata": intent.metadata,
                "client_secret": intent.client_secret,
            }

        except stripe.error.StripeError as e:
            logger.error("Stripe Intent retrieval failed: %s", e)
            raise

    def verify_webhook(self, payload: bytes, sig_header: str) -> dict:
        """Verifies signature and returns the event dictionary"""
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )

            return {
                "type": event["type"],
                "data": event["data"]
            }

        except (ValueError, stripe.error.SignatureVerificationError):
            raise ValueError("Invalid Stripe Signature")