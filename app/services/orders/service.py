"""
Order Service — Enterprise Business Logic & State Machine (GST & Auto-Discount Ready)
=====================================================================================
Path: app/services/orders/service.py

Architecture & Upgrades:
  ✅ Smart Sanitization — Preserves item names, HSN codes, GST slabs, and compare prices before stripping joins.
  ✅ Auto-Discount Enrichment — Dynamically computes item-level and total order discounts without DB changes.
  ✅ ABAC Policy Guardrails — Fully enforces view, cancellation, and invoice download permissions.
  ✅ ACID State Machine — Validates strict transition graphs and handles automated Stripe refunds.
"""
import logging
from typing import Any, Dict, Tuple, List
from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.repositories.order_repo import AsyncOrderRepository
from app.repositories.user_repo import AsyncUserRepository
from app.permissions.policies.order_policies import OrderPolicy
from app.events.registry import get_event_bus, OrderShippedEvent, OrderStatusChangedEvent
from app.integrations.payments.registry import get_payment_provider
from app.utils.documents.pdf_invoice import build_invoice_pdf
from app.enums.order_status import OrderStatus
from app.constants.order_messages import OrderMessages, OrderSecurityMessages

logger = logging.getLogger(__name__)

STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
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

    # ── Internal Helper: Auto-Inject Discount Fields ─────────────────────────
    def _enrich_item_discount(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dynamically computes and injects exact discount_amount and discount_percentage
        into order items for invoice generators and frontend payloads.
        """
        if not item:
            return item
        try:
            price = float(item.get("price") or 0.0)
            compare = float(item.get("compare_price") or 0.0)
            if compare > price > 0:
                disc_amt = round(compare - price, 2)
                disc_pct = int(round((disc_amt / compare) * 100))
            else:
                disc_amt = 0.0
                disc_pct = 0
            item["discount_amount"] = disc_amt
            item["discount_percentage"] = disc_pct
        except (ValueError, TypeError):
            item["discount_amount"] = 0.0
            item["discount_percentage"] = 0
        return item

    def _sanitize(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Strips internal system ledger fields, masks payment identifiers, maps GST/HSN, and enriches discounts."""
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
            
        total_order_discount = 0.0

        for item in sanitized.get("order_items", []):
            if "products" in item and isinstance(item["products"], dict):
                prod = item["products"]
                
                # 🔥 UPGRADE: Extract and preserve critical product & tax fields before deleting join payload!
                item["name"] = item.get("name") or prod.get("name") or "Product Item"
                item["hsn_code"] = item.get("hsn_code") or prod.get("hsn_code") or "9988"
                item["gst_percentage"] = item.get("gst_percentage") or prod.get("gst_percentage") or 18
                
                # Ensure price and compare_price exist before computing discount
                item["price"] = item.get("price") if item.get("price") is not None else prod.get("price")
                item["compare_price"] = item.get("compare_price") or prod.get("compare_price")
                
                item["product_slug"] = prod.get("slug")
                item["product_image_url"] = prod.get("image_url")
                del item["products"]
            
            # 🔥 Auto-Enrich Discount for each item
            self._enrich_item_discount(item)
            
            # Aggregate total discount for the order based on quantity
            try:
                qty = int(item.get("quantity") or 1)
                total_order_discount += item.get("discount_amount", 0.0) * qty
            except (ValueError, TypeError):
                pass

        # Inject aggregate discount at order root level
        if "order_items" in sanitized:
            sanitized["total_discount_amount"] = round(total_order_discount, 2)
                
        return sanitized

    async def get_user_orders(self, user_id: str, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        items, total = await self.repo.get_user_orders(user_id, status_filter, page, page_size)
        return [self._sanitize(o) for o in items], total

    async def get_order(self, order_id: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_id)
        
        # 🛡️ Enforce ABAC View Policy
        order = OrderPolicy.assert_can_view(raw_order, user_id, is_admin=is_admin)
        return self._sanitize(order)

    async def cancel_order(self, order_id: str, user_id: str, is_admin: bool = False) -> Dict[str, Any]:
        raw_order = await self.repo.get_order_by_id(order_id)
        if not raw_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=OrderSecurityMessages.ORDER_NOT_FOUND)

        # 🛡️ Enforce ABAC Cancellation Policy
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

        # Trigger Event Bus Dispatchers
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

        # 🛡️ Enforce ABAC Invoice Download Rules
        OrderPolicy.assert_can_download_invoice(raw_order, user_id, is_admin=is_admin)

        customer = await self.user_repo.get_user_by_id(raw_order.get("customer_id", "")) or {}
        try:
            return await run_in_threadpool(build_invoice_pdf, raw_order, customer)
        except Exception as exc:
            logger.error(f"PDF generator failure for order {order_id}: {exc}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=OrderSecurityMessages.PDF_GENERATION_FAILED)