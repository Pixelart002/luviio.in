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
from app.domains.orders.repository import AsyncOrderRepository
from app.domains.users.repository import AsyncUserRepository
from app.enums.order_status import OrderStatus
from app.events.bus import OrderShippedEvent, OrderStatusChangedEvent, get_event_bus
from app.permissions.policies.order_policies import OrderPolicy
from app.utils.documents.pdf_invoice import build_invoice_pdf

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
            get_event_bus().publish(OrderStatusChangedEvent(order=updated, customer_id=user_id, old_status=actual_old_status, new_status=OrderStatus.CANCELLED.value))
        except Exception as e:
            logger.error(f"Event bus dispatch failed during order cancel: {e}")
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
                try:
                    await self.payment_port.refund_payment_intent(current_res["stripe_payment_intent"])
                except Exception as e:
                    logger.error(f"Stripe refund execution failed: {e}")
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
                get_event_bus().publish(OrderShippedEvent(order=result, customer_email=email, customer_id=current_res["customer_id"], tracking_number=payload_data.get("tracking_number")))
        elif target_status_str in (OrderStatus.DELIVERED.value, OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value):
            get_event_bus().publish(OrderStatusChangedEvent(order=result, customer_id=current_res["customer_id"], old_status=current_status_enum.value, new_status=target_status_str))
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
            invoice_order["billing_snapshot"] = invoice.get("billing_snapshot") or {}
            invoice_order["shipping_snapshot"] = invoice.get("shipping_snapshot") or {}
            invoice_order["seller_snapshot"] = seller_snapshot
            invoice_order["qr_payload"] = invoice.get("qr_payload")
            invoice_order["order_items"] = invoice.get("invoice_items") or []
            pdf_bytes = await run_in_threadpool(build_invoice_pdf, invoice_order, customer)
            return pdf_bytes, invoice_order["invoice_number"]
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"PDF generator failure for order reference {order_identifier}: {exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=OrderSecurityMessages.PDF_GENERATION_FAILED)
