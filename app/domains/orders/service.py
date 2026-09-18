"""
Order Domain Service — Enterprise Business Logic & State Machine.
"""
import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.constants.order_messages import OrderMessages, OrderSecurityMessages
from app.domains.inventory.service import InventoryService
from app.domains.orders.exceptions import OrderRepositoryError
from app.domains.orders.payment_port import OrderPaymentPort
from app.domains.payments.repository import AsyncPaymentRepository
from app.domains.orders.repository import AsyncOrderRepository
from app.domains.users.repository import AsyncUserRepository
from app.enums.order_status import OrderStatus
from app.events.bus import OrderShippedEvent, OrderStatusChangedEvent, get_event_bus
from app.permissions.policies.order_policies import OrderPolicy
from app.utils.documents.snapshot_invoice_pdf import build_snapshot_invoice_pdf

logger = logging.getLogger(__name__)

STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.REFUNDED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.REFUNDED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(),
    OrderStatus.CANCELLED: set(),
}

_INTERNAL_FIELDS = {"id", "idempotency_key", "updated_at"}
_MASKED_FIELDS = {"stripe_payment_intent": lambda v: f"pi_***{v[-4:]}" if v and len(v) > 4 else None}


class OrderService:
    def __init__(self, payment_port: OrderPaymentPort | None = None):
        self.repo = AsyncOrderRepository()
        self.user_repo = AsyncUserRepository()
        self.inventory = InventoryService()
        self.payment_port = payment_port
        self.payment_repo = AsyncPaymentRepository()

    def _sanitize(self, order: Dict[str, Any]) -> Dict[str, Any]:
        if not order:
            return order
        sanitized = {k: v for k, v in order.items() if k not in _INTERNAL_FIELDS}
        for field, mask_fn in _MASKED_FIELDS.items():
            if field in sanitized:
                sanitized[field] = mask_fn(sanitized[field])
        if "order_items" in sanitized:
            sanitized["order_items"] = [
                {k: v for k, v in item.items() if k not in {"id", "order_id", "product_id", "created_at", "updated_at"}}
                for item in sanitized["order_items"]
            ]
        for item in sanitized.get("order_items", []):
            if "products" in item and isinstance(item["products"], dict):
                prod = item["products"]
                item["name"] = item.get("product_name") or prod.get("name") or "Product Item"
                if item.get("hsn_code") is None and prod.get("hsn_code") is not None:
                    item["hsn_code"] = prod.get("hsn_code")
                if item.get("gst_percentage") is None and prod.get("gst_percentage") is not None:
                    item["gst_percentage"] = prod.get("gst_percentage")
                if item.get("compare_price") is None and prod.get("compare_price") is not None:
                    item["compare_price"] = prod.get("compare_price")
                item["product_slug"] = prod.get("slug")
                item["product_image_url"] = prod.get("image_url")
                del item["products"]
        return sanitized

    async def get_user_orders(self, user_id: str, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        try:
            items, total = await self.repo.get_user_orders(user_id, status_filter, page, page_size)
        except OrderRepositoryError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return [self._sanitize(o) for o in items], total

    async def get_order(self, order_identifier: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_identifier)
        order = OrderPolicy.assert_can_view(raw_order, user_id, is_admin=is_admin)
        return self._sanitize(order)

    async def cancel_order(self, order_identifier: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_identifier)
        if not raw_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)
        OrderPolicy.assert_can_cancel(raw_order, user_id, is_admin=is_admin)
        internal_order_id = str(raw_order["id"])
        actual_old_status = raw_order.get("status", OrderStatus.PENDING.value)
        updated = await self.inventory.cancel_order_with_stock_restoration(
            internal_order_id,
            user_id if not is_admin else None,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)
        try:
            await get_event_bus().publish_durable(
                OrderStatusChangedEvent(
                    order=updated,
                    customer_id=user_id,
                    old_status=actual_old_status,
                    new_status=OrderStatus.CANCELLED.value,
                )
            )
        except Exception:
            logger.error("Durable event dispatch failed during order cancel", exc_info=True)
        return {"status": OrderStatus.CANCELLED.value, "order_number": raw_order.get("order_number", ""), "message": OrderMessages.CANCEL_SUCCESS}

    async def get_all_orders(self, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        try:
            items, total = await self.repo.get_all_orders(status_filter, page, page_size)
        except OrderRepositoryError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        return [self._sanitize(o) for o in items], total

    async def admin_update_order(self, order_identifier: str, payload_data: Dict[str, Any]) -> Dict[str, Any]:
        current_order = await self.repo.get_order_by_id(order_identifier)
        if not current_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)
        internal_order_id = str(current_order["id"])
        current_res = await self.repo.get_order_for_admin_update(internal_order_id)
        if not current_res:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)
        try:
            current_status_enum = OrderStatus(current_res["status"])
        except ValueError:
            current_status_enum = OrderStatus.PENDING
        target_status_str = payload_data.get("status")
        if target_status_str:
            try:
                target_status_enum = OrderStatus(target_status_str)
            except ValueError:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=OrderSecurityMessages.INVALID_TRANSITION)
            allowed_transitions = STATUS_TRANSITIONS.get(current_status_enum, set())
            if target_status_enum not in allowed_transitions:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_TRANSITION)
            if target_status_enum == OrderStatus.REFUNDED and current_res.get("stripe_payment_intent"):
                if self.payment_port is None:
                    logger.error("Order refund requested without a configured payment port")
                    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=OrderSecurityMessages.REFUND_FAILED)
                provider_key = str(current_res.get("payment_provider") or "stripe").strip().lower()
                provider_payment_id = str(current_res.get("provider_payment_id") or current_res.get("stripe_payment_intent") or "").strip()
                if not provider_payment_id:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.REFUND_FAILED)
                refund_amount = float(current_res.get("total_amount") or 0)
                try:
                    refund_attempt = await self.payment_repo.create_refund_attempt(
                        order_id=internal_order_id,
                        provider=provider_key,
                        provider_payment_id=provider_payment_id,
                        amount=refund_amount,
                        currency=str(current_res.get("currency") or "INR"),
                        idempotency_key=f"luviio-admin-refund-{internal_order_id}",
                        reference=str(current_res.get("order_number") or internal_order_id),
                        metadata={"source": "admin_order_refund"},
                    )
                    refund_attempt_id = str(refund_attempt["id"])
                    refunded = await self.payment_port.refund_payment_intent(
                        provider_payment_id,
                        amount_paise=int(round(refund_amount * 100)),
                        idempotency_key=str(refund_attempt["idempotency_key"]),
                    )
                    provider_refund_id = refunded.get("id") if isinstance(refunded, dict) else None
                    provider_refund_status = str(refunded.get("status") or "succeeded").lower() if isinstance(refunded, dict) else "succeeded"
                    if provider_refund_status not in {"succeeded", "pending"}:
                        raise RuntimeError(f"Unexpected refund provider status: {provider_refund_status}")
                    completed = await self.payment_repo.complete_refund_attempt(
                        refund_attempt_id,
                        provider_refund_status,
                        provider_refund_id=provider_refund_id,
                        metadata={"source": "admin_order_refund", "provider_status": provider_refund_status},
                    )
                    if provider_refund_status == "pending" or str(completed.get("status")) != "succeeded":
                        raise HTTPException(
                            status_code=status.HTTP_202_ACCEPTED,
                            detail="Refund is pending with the payment provider. The order will be settled after provider confirmation.",
                        )
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Stripe refund/accounting execution failed: {e}", exc_info=True)
                    try:
                        if 'refund_attempt_id' in locals():
                            await self.payment_repo.complete_refund_attempt(
                                refund_attempt_id,
                                "failed",
                                failure_code=str(getattr(e, "code", None) or type(e).__name__),
                                failure_message=str(e)[:1000],
                            )
                    except Exception:
                        logger.critical("Failed to persist admin refund failure", exc_info=True)
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=OrderSecurityMessages.REFUND_FAILED)
            if target_status_enum == OrderStatus.CANCELLED:
                result = await self.inventory.cancel_order_with_stock_restoration(internal_order_id)
                if not result:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)
            else:
                payload_data["status"] = target_status_enum.value
                result = await self.repo.update_order_status_safe(internal_order_id, payload_data, current_status_enum.value)
                if not result:
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)
        else:
            result = await self.repo.update_order_status_safe(internal_order_id, payload_data, current_status_enum.value)
            if not result:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)
        if target_status_str == OrderStatus.SHIPPED.value:
            email = await self.repo.get_user_email(current_res["customer_id"])
            if email:
                await get_event_bus().publish_durable(
                    OrderShippedEvent(
                        order=result,
                        customer_email=email,
                        customer_id=current_res["customer_id"],
                        tracking_number=payload_data.get("tracking_number"),
                    )
                )
        elif target_status_str in (OrderStatus.DELIVERED.value, OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value):
            await get_event_bus().publish_durable(
                OrderStatusChangedEvent(
                    order=result,
                    customer_id=current_res["customer_id"],
                    old_status=current_status_enum.value,
                    new_status=target_status_str,
                )
            )
        return self._sanitize(result)

    async def generate_invoice_pdf(self, order_identifier: str, user_id: str, is_admin: bool) -> tuple[bytes, str]:
        raw_order = await self.repo.get_order_by_id(order_identifier)
        if not raw_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)
        OrderPolicy.assert_can_download_invoice(raw_order, user_id, is_admin=is_admin)
        invoice_number = str(raw_order.get("invoice_number") or "").strip()
        if not invoice_number:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice number is not available for this order.")

        invoice = await self.repo.get_invoice_snapshot(str(raw_order["id"]))
        if not invoice:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Immutable invoice snapshot is not available for this paid order.")

        seller_snapshot = invoice.get("seller_snapshot") or {}
        if not seller_snapshot:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Invoice seller configuration is incomplete. Configure the registered seller legal details before generating GST invoices.")

        customer = await self.user_repo.get_user_by_id(raw_order.get("customer_id", "")) or {}
        try:
            invoice_order = dict(raw_order)
            invoice_order["id"] = str(raw_order.get("order_number") or order_identifier)
            invoice_order["invoice_number"] = invoice.get("invoice_number") or invoice_number
            invoice_order["issued_at"] = invoice.get("issued_at")
            invoice_order["currency"] = invoice.get("currency")
            invoice_order["tax_type"] = invoice.get("tax_type")
            totals = invoice.get("totals_snapshot") or {}
            invoice_order.update(totals)
            billing_snapshot = invoice.get("billing_snapshot") or {}
            shipping_snapshot = invoice.get("shipping_snapshot") or {}
            invoice_order["billing_snapshot"] = billing_snapshot
            invoice_order["shipping_snapshot"] = shipping_snapshot
            invoice_order["seller_snapshot"] = seller_snapshot
            invoice_order["qr_payload"] = invoice.get("qr_payload")
            invoice_order["order_items"] = invoice.get("invoice_items") or []
            pdf_bytes = await run_in_threadpool(
                build_snapshot_invoice_pdf,
                invoice_order,
                customer,
                seller_snapshot,
                billing_snapshot,
                shipping_snapshot,
            )
            return pdf_bytes, invoice_order["invoice_number"]
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"PDF generator failure for order reference {order_identifier}: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=OrderSecurityMessages.PDF_GENERATION_FAILED)
