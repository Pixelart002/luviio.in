"""
Orders domain ports.

The orders bounded context depends on a capability contract, not the concrete
payments domain. Concrete payment orchestration is supplied through an adapter
at the application/integration boundary.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class OrderPaymentPort(Protocol):
    """Capability required by Orders to start online checkout."""

    async def create_checkout(
        self,
        *,
        user_id: str,
        client_ip: str,
        idempotency_key: str,
        address_id: str,
        billing_address_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        coupon_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or resume the payment-backed checkout for an order."""
        ...
