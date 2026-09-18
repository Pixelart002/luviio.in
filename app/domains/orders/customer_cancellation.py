"""Customer order cancellation orchestration, including paid-order refunds."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import HTTPException, status

from app.constants.order_messages import OrderMessages, OrderSecurityMessages
from app.domains.inventory.customer_cancellation import release_stock_for_customer_cancellation
from app.domains.orders.payment_port import OrderPaymentPort
from app.domains.payments.repository import AsyncPaymentRepository
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
    started = time.perf_counter()
    service = OrderService()
    payment_repo = AsyncPaymentRepository()
    raw_order_started = time.perf_counter()
    raw_order = await service.repo.get_order_by_id(order_identifier)
    logger.info("Cancellation timing | step=load_order order=%s duration_ms=%.2f", order_identifier, (time.perf_counter() - raw_order_started) * 1000)
    if not raw_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

    OrderPolicy.assert_can_view(raw_order, user_id)
    current_status = str(raw_order.get("status", "")).lower()
    old_status = current_status

    if current_status == OrderStatus.PENDING.value:
        step_started = time.perf_counter()
        result = await release_stock_for_customer_cancellation(str(raw_order["id"]), user_id, "cancelled")
        logger.info("Cancellation timing | step=inventory_cancel order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
        target_status = OrderStatus.CANCELLED.value
    elif current_status in {OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
        payment_method = str(raw_order.get("payment_method") or "").strip().lower()
        payment_provider = str(raw_order.get("payment_provider") or "").strip().lower()
        is_cod = payment_method == "cod" or payment_provider == "cod"

        if is_cod:
            # COD is an offline payment method; there is no Stripe PaymentIntent to refund.
            # Cancellation therefore releases the reserved stock without invoking the
            # Stripe refund port. Any cash already collected is handled outside Stripe.
            step_started = time.perf_counter()
            result = await release_stock_for_customer_cancellation(
                str(raw_order["id"]), user_id, "cancelled"
            )
            logger.info("Cancellation timing | step=inventory_cancel_cod order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
            target_status = OrderStatus.CANCELLED.value
        else:
            payment_intent = str(raw_order.get("stripe_payment_intent") or "").strip()
            if not payment_intent:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Paid order cannot be cancelled because its payment reference is missing.",
                )

            try:
                step_started = time.perf_counter()
                refunded = await payment_port.refund_payment_intent(payment_intent)
                logger.info("Cancellation timing | step=provider_refund order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
            except Exception as exc:
                logger.error(
                    "Customer cancellation refund failed for order %s: %s",
                    raw_order.get("order_number", order_identifier),
                    exc,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=OrderSecurityMessages.REFUND_FAILED,
                ) from exc
            if refunded is False:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=OrderSecurityMessages.REFUND_FAILED,
                )

            try:
                step_started = time.perf_counter()
                await payment_repo.record_refund_accounting(
                    order_id=str(raw_order["id"]),
                    provider=payment_provider,
                    provider_payment_id=payment_intent,
                    amount=float(raw_order.get("total_amount") or 0),
                    currency=str(raw_order.get("currency") or "INR"),
                    reference=payment_intent,
                    metadata={"source": "customer_cancellation"},
                )
                logger.info("Cancellation timing | step=refund_accounting order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
            except Exception as exc:
                logger.error(
                    "Provider refund succeeded but payment accounting failed for order %s: %s",
                    raw_order.get("order_number", order_identifier),
                    exc,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Payment was refunded by the provider, but internal payment accounting is pending reconciliation.",
                ) from exc

            step_started = time.perf_counter()
            result = await release_stock_for_customer_cancellation(
                str(raw_order["id"]), user_id, "refunded"
            )
            logger.info("Cancellation timing | step=inventory_refund order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
            if not result:
                logger.error(
                    "Refund succeeded but refunded inventory settlement failed for order %s",
                    raw_order.get("order_number", order_identifier),
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment was refunded, but order settlement is still pending reconciliation.",
                )
            target_status = OrderStatus.REFUNDED.value
    else:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)

    if not result:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)

    try:
        step_started = time.perf_counter()
        await get_event_bus().publish_durable(OrderStatusChangedEvent(order=result, customer_id=user_id, old_status=old_status, new_status=target_status))
        logger.info("Cancellation timing | step=outbox_publish order=%s duration_ms=%.2f", raw_order.get("order_number", order_identifier), (time.perf_counter() - step_started) * 1000)
    except Exception:
        logger.error("Durable event dispatch failed during customer order cancellation", exc_info=True)

    logger.info("Cancellation timing | step=total order=%s duration_ms=%.2f status=%s", raw_order.get("order_number", order_identifier), (time.perf_counter() - started) * 1000, target_status)
    return {
        "status": target_status,
        "order_number": raw_order.get("order_number", ""),
        "message": "Order cancelled and payment refund initiated successfully." if target_status == OrderStatus.REFUNDED.value else OrderMessages.CANCEL_SUCCESS,
    }
