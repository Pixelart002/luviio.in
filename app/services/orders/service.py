"""
Order Service — Enterprise Business Logic & State Machine (GST Ready)
=====================================================================
Path: app/services/orders/service.py
"""
import logging
from typing import Any, Dict, Tuple, Optional, List
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool
from decimal import Decimal, ROUND_HALF_UP

from app.repositories.order_repo import AsyncOrderRepository
from app.repositories.user_repo import AsyncUserRepository
from app.permissions.policies.order_policy import OrderPolicy
from app.events.bus import get_event_bus, OrderShippedEvent, OrderStatusChangedEvent
from app.integrations.payments.registry import get_payment_provider
from app.utils.documents.pdf_invoice import build_invoice_pdf
from app.enums.order_status import OrderStatus
from app.constants.order_messages import OrderMessages, OrderSecurityMessages

logger = logging.getLogger(__name__)

# 🔥 UPDATED: Finite State Machine (FSM) Matrix for Order Lifecycles
STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    # Paid order can move to Processing, Shipped, Cancelled, or be Refunded directly.
    OrderStatus.PAID: {OrderStatus.PROCESSING, OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    # Processing means warehouse is packing it. From here, it ships or gets cancelled/refunded.
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(), 
    OrderStatus.CANCELLED: set(),
}

_INTERNAL_FIELDS = {"idempotency_key", "updated_at"}
_MASKED_FIELDS = {"stripe_payment_intent": lambda v: f"pi_***{v[-4:]}" if v and len(v) > 4 else None}

class OrderService:
    def __init__(self):
        self.repo = AsyncOrderRepository()
        self.user_repo = AsyncUserRepository()

    def _sanitize(self, order: Dict[str, Any]) -> Dict[str, Any]:
        if not order: 
            return order
        sanitized = {k: v for k, v in order.items() if k not in _INTERNAL_FIELDS}
        for field, mask_fn in _MASKED_FIELDS.items():
            if field in sanitized: 
                sanitized[field] = mask_fn(sanitized[field])
                
        if "order_items" in sanitized:
            sanitized["order_items"] = [
                {k: v for k, v in item.items() if k not in {"order_id", "created_at", "updated_at"}} 
                for item in sanitized["order_items"]
            ]
            
        for item in sanitized.get("order_items", []):
            if "products" in item and isinstance(item["products"], dict):
                prod = item["products"]
                item["name"] = item.get("product_name") or prod.get("name") or "Product Item"
                item["hsn_code"] = item.get("hsn_code") or prod.get("hsn_code") or "9988"
                item["gst_percentage"] = item.get("gst_percentage") or prod.get("gst_percentage") or 18
                item["compare_price"] = item.get("compare_price") or prod.get("compare_price")
                item["product_slug"] = prod.get("slug")
                item["product_image_url"] = prod.get("image_url")
                del item["products"]
                
        return sanitized

    async def create_order_from_cart(self, user_id: str, address_id: str, notes: Optional[str] = None, idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """Reads user cart, calculates GST/Discounts, locks snapshots, and creates order."""
        cart_data = await self.repo.get_cart_for_checkout(user_id)
        if not cart_data or not cart_data.get("cart_items"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your cart is empty. Cannot initiate checkout.")

        total_subtotal = Decimal("0.00")
        total_tax = Decimal("0.00")
        total_discount = Decimal("0.00")
        items_payload = []

        for item in cart_data["cart_items"]:
            prod = item.get("products")
            if not prod:
                continue

            qty = item["quantity"]
            if prod["stock"] < qty:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Insufficient stock for item: {prod['name']}")

            unit_price = Decimal(str(prod["price"]))
            compare_price = Decimal(str(prod["compare_price"] or unit_price))
            subtotal = unit_price * qty

            # Discount Math
            discount_per_item = max(Decimal("0.00"), compare_price - unit_price)
            discount_amount = discount_per_item * qty

            # GST Math
            gst_pct = Decimal(str(prod.get("gst_percentage") or 18))
            tax_amount = (subtotal * (gst_pct / Decimal("100"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            total_subtotal += subtotal
            total_tax += tax_amount
            total_discount += discount_amount

            items_payload.append({
                "product_id": prod["id"],
                "product_name": prod["name"],
                "unit_price": float(unit_price),
                "quantity": qty,
                "subtotal": float(subtotal),
                "compare_price": float(compare_price),
                "hsn_code": prod.get("hsn_code") or "9988",
                "gst_percentage": int(gst_pct),
                "tax_amount": float(tax_amount),
                "discount_amount": float(discount_amount)
            })

        shipping_cost = Decimal("0.00") if total_subtotal >= Decimal("999.00") else Decimal("99.00")
        total_amount = total_subtotal + total_tax + shipping_cost

        order_data = {
            "customer_id": user_id,
            "status": OrderStatus.PENDING.value,
            "subtotal": float(total_subtotal),
            "shipping_cost": float(shipping_cost),
            "tax_amount": float(total_tax),
            "total_amount": float(total_amount),
            "shipping_address_id": str(address_id),
            "notes": notes,
            "idempotency_key": idempotency_key,
            "currency": "INR",
            "tax_type": "IGST"
        }

        created_order = await self.repo.create_order_with_items(order_data, items_payload, user_id)
        if not created_order:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create order due to database conflict.")

        return self._sanitize(created_order)

    async def get_user_orders(self, user_id: str, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        items, total = await self.repo.get_user_orders(user_id, status_filter, page, page_size)
        return [self._sanitize(o) for o in items], total

    async def get_order(self, order_id: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_id)
        order = OrderPolicy.assert_can_view(raw_order, user_id, is_admin=is_admin)
        return self._sanitize(order)

    async def cancel_order(self, order_id: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_id)
        if not raw_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        OrderPolicy.assert_can_cancel(raw_order, user_id, is_admin=is_admin)

        actual_old_status = raw_order.get("status", OrderStatus.PENDING.value)
        updated = await self.repo.cancel_order_and_restore_stock(order_id, user_id if not is_admin else None)
        
        if not updated: 
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)

        try:
            get_event_bus().publish(OrderStatusChangedEvent(
                order=updated, customer_id=user_id, 
                old_status=actual_old_status, new_status=OrderStatus.CANCELLED.value
            ))
        except Exception as e: 
            logger.error(f"Event bus dispatch failed during order cancel: {e}")
            
        return {"status": OrderStatus.CANCELLED.value, "order_id": order_id, "message": OrderMessages.CANCEL_SUCCESS}

    async def get_all_orders(self, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        items, total = await self.repo.get_all_orders(status_filter, page, page_size)
        return [self._sanitize(o) for o in items], total

    async def admin_update_order(self, order_id: str, payload_data: Dict[str, Any]) -> Dict[str, Any]:
        current_res = await self.repo.get_order_for_admin_update(order_id)
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
                try: 
                    await run_in_threadpool(get_payment_provider("stripe").process_refund, current_res["stripe_payment_intent"])
                except Exception as e: 
                    logger.error(f"Stripe refund execution failed: {e}")
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=OrderSecurityMessages.REFUND_FAILED)

            if target_status_enum == OrderStatus.CANCELLED:
                result = await self.repo.cancel_order_and_restore_stock(order_id)
                if not result: 
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.INVALID_CANCEL_STATE)
            else:
                payload_data["status"] = target_status_enum.value
                result = await self.repo.update_order_status_safe(order_id, payload_data, current_status_enum.value)
                if not result: 
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)
        else:
            result = await self.repo.update_order_status_safe(order_id, payload_data, current_status_enum.value)
            if not result:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=OrderSecurityMessages.CONCURRENCY_CONFLICT)

        if target_status_str == OrderStatus.SHIPPED.value:
            email = await self.repo.get_user_email(current_res["customer_id"])
            if email: 
                get_event_bus().publish(OrderShippedEvent(
                    order=result, customer_email=email, customer_id=current_res["customer_id"], 
                    tracking_number=payload_data.get("tracking_number")
                ))
        elif target_status_str in (OrderStatus.DELIVERED.value, OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value):
            get_event_bus().publish(OrderStatusChangedEvent(
                order=result, customer_id=current_res["customer_id"], 
                old_status=current_status_enum.value, new_status=target_status_str
            ))

        return self._sanitize(result)

    async def generate_invoice_pdf(self, order_id: str, user_id: str, is_admin: bool) -> bytes:
        raw_order = await self.repo.get_order_by_id(order_id)
        if not raw_order: 
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        OrderPolicy.assert_can_download_invoice(raw_order, user_id, is_admin=is_admin)
        customer = await self.user_repo.get_user_by_id(raw_order.get("customer_id", "")) or {}
        try:
            return await run_in_threadpool(build_invoice_pdf, raw_order, customer)
        except Exception as exc:
            logger.error(f"PDF generator failure for order {order_id}: {exc}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=OrderSecurityMessages.PDF_GENERATION_FAILED)