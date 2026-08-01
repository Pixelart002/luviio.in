"""
Stripe Implementation
=====================
Path: app/integrations/payments/stripe_impl.py
"""
import logging
import stripe
from typing import Any, Dict
from app.core.config import settings
from app.integrations.payments.base import PaymentProvider

logger = logging.getLogger(__name__)

if getattr(settings, "STRIPE_SECRET_KEY", None):
    stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeProvider(PaymentProvider):
    def create_payment_intent(
        self,
        amount_paise: int,
        currency: str,
        order_id: str,
        user_id: str,
        idem_key: str,
    ) -> Dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_paise,
                currency=currency.lower(),
                metadata={
                    "order_id": order_id,
                    "user_id": user_id,
                },
                automatic_payment_methods={"enabled": True},
                description=f"{getattr(settings, 'APP_NAME', 'Luviio Commerce')} — Order #{order_id[:8].upper()}",
                idempotency_key=idem_key,
            )

            client_secret = (
                intent.get("client_secret")
                if isinstance(intent, dict)
                else getattr(intent, "client_secret", None)
            )

            if not client_secret:
                raise RuntimeError("Stripe did not return a client_secret for the new PaymentIntent")

            return {
                "client_secret": client_secret,
                "id": intent.id,
                "status": intent.status,
            }
        except stripe.error.StripeError as e:
            logger.error("Stripe Intent creation failed: %s", e)
            raise

    def update_intent_metadata(self, intent_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.modify(intent_id, metadata=metadata)
            return {
                "id": intent.id,
                "status": intent.status,
            }
        except stripe.error.StripeError as e:
            logger.error("Stripe Intent modify failed: %s", e)
            raise

    def retrieve_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
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

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=getattr(settings, "STRIPE_WEBHOOK_SECRET", ""),
            )
            return {
                # 🔥 FIX: event id is required for webhook-delivery idempotency
                # (Stripe retries webhooks on any non-2xx / timeout response,
                # so without this we have no way to detect "already processed").
                "id": event["id"],
                "type": event["type"],
                "data": event["data"],
            }
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            logger.error("Webhook signature verification failed: %s", e)
            raise ValueError("Invalid Stripe Signature") from e

    def process_refund(self, payment_intent_id: str) -> bool:
        try:
            refund = stripe.Refund.create(payment_intent=payment_intent_id)
            return refund.status in {"succeeded", "pending"}
        except stripe.error.StripeError as e:
            logger.error("Stripe Refund failed: %s", e)
            return False

    # 🔥 NEW
    def cancel_intent(self, payment_intent_id: str) -> Dict[str, Any]:
        try:
            intent = stripe.PaymentIntent.cancel(payment_intent_id)
            return {
                "id": intent.id,
                "status": intent.status,
            }
        except stripe.error.StripeError as e:
            # Not fatal for the caller -- the intent may already be in a
            # state Stripe won't let us cancel (e.g. already succeeded, or
            # already canceled). Callers should log and continue with the
            # DB-side cancellation regardless.
            logger.warning("Stripe Intent cancel failed for %s: %s", payment_intent_id, e)
            raise