"""Payment adapter implementing the Orders bounded-context port."""
from __future__ import annotations

from app.domains.orders.payment_port import OrderPaymentPort
from app.domains.payments.refund import refund_payment_intent


class PaymentsOrderAdapter(OrderPaymentPort):
    """Translate order refund capabilities to the Payments bounded context."""

    async def refund_payment_intent(
        self,
        payment_intent_id: str,
        amount_paise: int | None = None,
        idempotency_key: str | None = None,
        reason: str | None = None,
    ) -> object:
        return await refund_payment_intent(
            payment_intent_id,
            amount_paise=amount_paise,
            idempotency_key=idempotency_key,
            reason=reason,
        )
