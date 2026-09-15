"""Adapter wiring the order payment port to the payments bounded context."""
from __future__ import annotations

from app.domains.payments.refund import refund_payment_intent


class PaymentsOrderAdapter:
    """Infrastructure/application wiring kept outside OrderService."""

    async def refund_payment_intent(self, payment_intent_id: str) -> object:
        return await refund_payment_intent(payment_intent_id)
