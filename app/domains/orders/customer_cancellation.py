"""Customer order cancellation orchestration, including paid-order refunds."""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import HTTPException, status

from app.constants.order_messages import OrderMessages, OrderSecurityMessages
from app.domains.orders.payment_port import OrderPaymentPort
from app.domains.orders.service import OrderService
from app.enums.order_status import OrderStatus
from app.events.bus import OrderStatusChangedEvent, get_event_bus
from app.permissions.policies.order_policies import OrderPolicy

logger = logging.getLogger(__name__)


async def cancel_customer_order(
    order_identifier: str,
    user_id: str,
    payment_port: OrderPaymentPort,
) -> Dict[str, Any]:
    """Cancel a customer order safely; paid/processing orders are refunded first."""
    service = OrderService()
    raw_order = await service.repo.get_order_by_id(order_identifier)
    if not raw_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

    OrderPolicy.assert_can_view(raw_order, user_id)
    current_status = str(raw_order.get("status", "")).lower()
    old_status = current_status

    if current_status == OrderStatus.PENDING.value:
        result = await service.inventory.cancel_order_with_stock_restoration(str(raw_order["id"]), user_id)
        target_status = OrderStatus.CANCELLED.value
    elif current_status in {OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
        payment_intent = str(raw_order.get("stripe_payment_intent") or "").strip()
        if not payment_intent:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Paid order cannot be cancelled because its payment reference is missing.")

        try:
            refunded = await payment_port.refund_payment_intent(payment_intent)
        except Exception as exc:
            logger.error("Customer cancellation refund failed for order %s: %s", raw_order.get("order_number", order_identifier), exc, exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=OrderSecurityMessages.REFUND_FAILED) from exc
        if refunded is False:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=OrderSecurityMessages.REFUND_FAILED)

        result = await service.inventory.cancel_order_with_stock_restoration(str(raw_order["id"]), user_id)
        if not result:
            logger.error("Refund succeeded but inventory/order cancellation failed for order %s", raw_order.get("order_number", order_identifier))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment was refunded, but order settlement is still pending reconciliation.")

        result = await service.repo.update_order_status_safe(str(raw_order["id"]), {"status": OrderStatus.REFUNDED.value}, OrderStatus.CANCELLED.value)
        if not result:
            logger.error("Refund and stock restoration succeeded but refunded status update failed for order %s", raw_order.get("order_number", order_identifier))
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment was refunded and stock restored; order status is pending reconciliation.")
        target_status = OrderStatus.REFUNDED.value
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)

    if not result:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)

    try:
        await get_event_bus().publish_durable(OrderStatusChangedEvent(order=result, customer_id=user_id, old_status=old_status, new_status=target_status))
    except Exception:
        logger.error("Durable event dispatch failed during customer order cancellation", exc_info=True)

    return {
        "status": target_status,
        "order_number": raw_order.get("order_number", ""),
        "message": "Order cancelled and payment refund initiated successfully." if target_status == OrderStatus.REFUNDED.value else OrderMessages.CANCEL_SUCCESS,
    }
