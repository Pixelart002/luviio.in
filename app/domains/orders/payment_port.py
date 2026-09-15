"""Payment port used by the order domain.

The order domain depends on this small protocol rather than importing the
payments implementation directly. Runtime wiring is supplied by the router.
"""
from __future__ import annotations

from typing import Protocol


class OrderPaymentPort(Protocol):
    async def refund_payment_intent(self, payment_intent_id: str) -> object:
        """Refund a captured payment for an order lifecycle operation."""
        ...
