"""Adapter that keeps Orders independent from the Payments domain implementation."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.domains.orders.ports import OrderPaymentPort
from app.domains.payments.service import PaymentService


class PaymentOrderPortAdapter(OrderPaymentPort):
    """Translate the Orders checkout capability into PaymentService calls."""

    def __init__(self, payment_service: Optional[PaymentService] = None) -> None:
        self._payment_service = payment_service or PaymentService()

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
        return await self._payment_service.create_intent(
            user_id=user_id,
            client_ip=client_ip,
            idempotency_key=idempotency_key,
            address_id=address_id,
            billing_address_id=billing_address_id,
            user_agent=user_agent,
            coupon_code=coupon_code,
        )
