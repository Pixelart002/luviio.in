"""Checkout application orchestration.

This layer owns cross-domain checkout use-cases. Business rules remain in the
respective domains; this service only coordinates them.
"""
from typing import Any, Dict, Optional

from app.domains.checkout.cod_service import CodOrderService
from app.domains.payments.service import PaymentService


class CheckoutService:
    """Application-level checkout use cases."""

    async def create_online_order(
        self,
        *,
        user_id: str,
        client_ip: str,
        idempotency_key: str,
        address_id: str,
        billing_address_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        coupon_code: Optional[str] = None,
        shipping_courier_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await PaymentService().create_intent(
            user_id=user_id,
            client_ip=client_ip,
            idempotency_key=idempotency_key,
            address_id=address_id,
            billing_address_id=billing_address_id,
            user_agent=user_agent,
            coupon_code=coupon_code,
            shipping_courier_id=shipping_courier_id,
        )

    async def create_cod_order(
        self,
        *,
        user_id: str,
        address_id: str,
        idempotency_key: str,
        coupon_code: Optional[str] = None,
        shipping_courier_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await CodOrderService().create_order(
            user_id=user_id,
            address_id=address_id,
            idempotency_key=idempotency_key,
            coupon_code=coupon_code,
            shipping_courier_id=shipping_courier_id,
        )
