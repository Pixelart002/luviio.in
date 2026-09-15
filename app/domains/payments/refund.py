"""Payment-domain refund operations.

Keeps external payment-provider calls inside the payments bounded context.
"""
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.integrations.payments.registry import get_payment_provider


async def refund_payment_intent(payment_intent_id: str) -> Any:
    """Refund a Stripe PaymentIntent without exposing provider details to other domains."""
    if not payment_intent_id or not isinstance(payment_intent_id, str):
        raise ValueError("PaymentIntent ID is required")
    provider = get_payment_provider("stripe")
    return await run_in_threadpool(provider.process_refund, payment_intent_id)
