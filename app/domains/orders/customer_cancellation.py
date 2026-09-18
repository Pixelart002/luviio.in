"""Customer order cancellation orchestration, including paid-order refunds."""
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import uuid4

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
    service = OrderService()
    payment_repo = AsyncPaymentRepository()
    raw_order = await service.repo.get_order_by_id(order_identifier)
    if not raw_order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

    OrderPolicy.assert_can_view(raw_order, user_id)
    current_status = str(raw_order.get("status", "")).lower()
    old_status = current_status

    if current_status == OrderStatus.PENDING.value:
        result = await release_stock_for_customer_cancellation(str(raw_order["id"]), user_id, "cancelled")
        target_status = OrderStatus.CANCELLED.value
    elif current_status in {OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
        payment_method = str(raw_order.get("payment_method") or "").strip().lower()
        payment_provider = str(raw_order.get("payment_provider") or "").strip().lower()
        is_cod = payment_method == "cod" or payment_provider == "cod"

        if is_cod:
            # COD is an offline payment method; there is no Stripe PaymentIntent to refund.
            # Cancellation therefore releases the reserved stock without invoking the
            # Stripe refund port. Any cash already collected is handled outside Stripe.
            result = await release_stock_for_customer_cancellation(
                str(raw_order["id"]), user_id, "cancelled"
            )
            target_status = OrderStatus.CANCELLED.value
        else:
            payment_intent = str(raw_order.get("stripe_payment_intent") or "").strip()
            if not payment_intent:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Paid order cannot be cancelled because its payment reference is missing.",
                )

            refund_amount = float(raw_order.get("total_amount") or 0)
            refund_attempt = await payment_repo.create_refund_attempt(
                order_id=str(raw_order["id"]),
                provider=payment_provider,
                provider_payment_id=payment_intent,
                amount=refund_amount,
                currency=str(raw_order.get("currency") or "INR"),
                idempotency_key=f"luviio-refund-{uuid4()}",
                reason="requested_by_customer",
                reference=str(raw_order.get("order_number") or order_identifier),
                metadata={"source": "customer_cancellation"},
            )
            refund_attempt_id = str(refund_attempt["id"])
            refund_idempotency_key = str(refund_attempt["idempotency_key"])
            try:
                refunded = await payment_port.refund_payment_intent(
                    payment_intent,
                    amount_paise=int(round(refund_amount * 100)),
                    idempotency_key=refund_idempotency_key,
                    reason="requested_by_customer",
                )
            except Exception as exc:
                try:
                    await payment_repo.complete_refund_attempt(
                        refund_attempt_id,
                        "failed",
                        failure_code=str(getattr(exc, "code", None) or type(exc).__name__),
                        failure_message=str(exc)[:1000],
                    )
                except Exception:
                    logger.critical("Failed to persist refund failure for attempt %s", refund_attempt_id, exc_info=True)
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
                await payment_repo.complete_refund_attempt(
                    refund_attempt_id,
                    "failed",
                    failure_code="PROVIDER_REFUND_FAILED",
                    failure_message="Payment provider returned a negative refund result.",
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=OrderSecurityMessages.REFUND_FAILED,
                )

            provider_refund_id = refunded.get("id") if isinstance(refunded, dict) else None
            provider_refund_status = str(refunded.get("status") or "succeeded").lower() if isinstance(refunded, dict) else "succeeded"
            if provider_refund_status not in {"succeeded", "pending"}:
                await payment_repo.complete_refund_attempt(
                    refund_attempt_id,
                    "failed",
                    provider_refund_id=provider_refund_id,
                    failure_code="PROVIDER_REFUND_UNEXPECTED_STATUS",
                    failure_message=provider_refund_status,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=OrderSecurityMessages.REFUND_FAILED,
                )

            completed_refund = await payment_repo.complete_refund_attempt(
                refund_attempt_id,
                provider_refund_status,
                provider_refund_id=provider_refund_id,
                metadata={"source": "customer_cancellation", "provider_status": provider_refund_status},
            )
            if provider_refund_status != "succeeded":
                raise HTTPException(
                    status_code=status.HTTP_202_ACCEPTED,
                    detail="Refund is pending with the payment provider. The order will be settled after provider confirmation.",
                )
            if str(completed_refund.get("status")) != "succeeded":
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Refund was created but internal refund accounting is pending reconciliation.",
                )

            result = await release_stock_for_customer_cancellation(
                str(raw_order["id"]), user_id, "refunded"
            )
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
        await get_event_bus().publish_durable(OrderStatusChangedEvent(order=result, customer_id=user_id, old_status=old_status, new_status=target_status))
    except Exception:
        logger.error("Durable event dispatch failed during customer order cancellation", exc_info=True)

    return {
        "status": target_status,
        "order_number": raw_order.get("order_number", ""),
        "message": "Order cancelled and payment refund initiated successfully." if target_status == OrderStatus.REFUNDED.value else OrderMessages.CANCEL_SUCCESS,
    }
