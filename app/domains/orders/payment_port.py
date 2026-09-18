"""Payment port used by the order domain.

The order domain depends on this small protocol rather than importing the
payments implementation directly. Runtime wiring is supplied by the router.
"""
from __future__ import annotations

from typing import Optional, Protocol


class OrderPaymentPort(Protocol):
    async def refund_payment_intent(
        self,
        payment_intent_id: str,
        amount_paise: Optional[int] = None,
        idempotency_key: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> object:
        """Refund a captured payment for an order lifecycle operation."""
        ...
