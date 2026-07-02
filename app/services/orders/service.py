import logging
from typing import Any, Dict, Tuple, List
from starlette.concurrency import run_in_threadpool

from app.repositories.order_repo import AsyncOrderRepository
from app.repositories.user_repo import AsyncUserRepository
from app.services.events import get_event_bus, OrderShippedEvent, OrderStatusChangedEvent
from app.integrations.payments.registry import get_payment_provider
from app.core.exceptions import ResourceNotFound, LuviioException
from app.utils.documents.pdf_invoice import build_invoice_pdf
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)

STATUS_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(), OrderStatus.CANCELLED: set(),
}

_INTERNAL_FIELDS = {"idempotency_key", "customer_id", "updated_at"}
_MASKED_FIELDS = {"stripe_payment_intent": lambda v: f"pi_***{v[-4:]}" if v and len(v) > 4 else None}

class OrderService:
    def __init__(self):
        self.repo = AsyncOrderRepository()
        self.user_repo = AsyncUserRepository()

    def _sanitize(self, order: dict) -> dict:
        if not order: return order
        sanitized = {k: v for k, v in order.items() if k not in _INTERNAL_FIELDS}
        for field, mask_fn in _MASKED_FIELDS.items():
            if field in sanitized: sanitized[field] = mask_fn(sanitized[field])
        if "order_items" in sanitized:
            sanitized["order_items"] = [{k: v for k, v in item.items() if k not in {"order_id", "created_at", "updated_at"}} for item in sanitized["order_items"]]
        for item in sanitized.get("order_items", []):
            if "products" in item and isinstance(item["products"], dict):
                item["product_slug"] = item["products"].get("slug")
                item["product_image_url"] = item["products"].get("image_url")
                del item["products"]
        return sanitized

    async def get_user_orders(self, user_id: str, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict], int]:
        items, total = await self.repo.get_user_orders(user_id, status_filter, page, page_size)
        return [self._sanitize(o) for o in items], total

    async def get_order(self, order_id: str, user_id: str) -> Dict[str, Any]:
        order = await self.repo.get_order_by_id(order_id, user_id)
        if not order: raise ResourceNotFound("Order")
        return self._sanitize(order)

    async def cancel_order(self, order_id: str, user_id: str) -> Dict[str, Any]:
        current_order = await self.repo.get_order_by_id(order_id, user_id)
        if not current_order: raise ResourceNotFound("Order")

        actual_old_status = current_order.get("status", OrderStatus.PENDING)
        updated = await self.repo.cancel_order_and_restore_stock(order_id, user_id)
        if not updated: raise LuviioException("Cannot cancel this order.", "INVALID_STATE", 409)

        try:
            get_event_bus().publish(OrderStatusChangedEvent(order=updated, customer_id=user_id, old_status=actual_old_status, new_status=OrderStatus.CANCELLED))
        except Exception as e: logger.error(f"Event bus failed: {e}")
        return {"status": OrderStatus.CANCELLED, "order_id": order_id}

    async def get_all_orders(self, status_filter: str, page: int, page_size: int) -> Tuple[List[Dict], int]:
        items, total = await self.repo.get_all_orders(status_filter, page, page_size)
        return [self._sanitize(o) for o in items], total

    async def admin_update_order(self, order_id: str, payload_data: Dict[str, Any]) -> Dict[str, Any]:
        current_res = await self.repo.get_order_for_admin_update(order_id)
        if not current_res: raise ResourceNotFound("Order")

        current_status = current_res["status"]
        target_status = payload_data.get("status")

        if target_status:
            allowed = STATUS_TRANSITIONS.get(current_status, set())
            if target_status not in allowed: 
                raise LuviioException(f"Cannot move '{current_status}' → '{target_status}'", "INVALID_TRANSITION", 409)
                
            if target_status == OrderStatus.REFUNDED and current_res.get("stripe_payment_intent"):
                try: await run_in_threadpool(get_payment_provider("stripe").process_refund, current_res["stripe_payment_intent"])
                except Exception as e: raise LuviioException(f"Refund failed: {e}", "REFUND_ERROR", 502)

            if target_status == OrderStatus.CANCELLED:
                result = await self.repo.cancel_order_and_restore_stock(order_id)
                if not result: raise LuviioException("Order cannot be cancelled", "INVALID_STATE", 409)
            else:
                result = await self.repo.update_order_status_safe(order_id, payload_data, current_status)
                if not result: raise LuviioException("Order modified — refresh and retry", "CONCURRENCY_ERROR", 409)
        else:
            result = await self.repo.update_order_status_safe(order_id, payload_data, current_status)

        if target_status == OrderStatus.SHIPPED:
            email = await self.repo.get_user_email(current_res["customer_id"])
            if email: get_event_bus().publish(OrderShippedEvent(order=result, customer_email=email, customer_id=current_res["customer_id"], tracking_number=payload_data.get("tracking_number")))
        elif target_status in (OrderStatus.DELIVERED, OrderStatus.REFUNDED, OrderStatus.CANCELLED):
            get_event_bus().publish(OrderStatusChangedEvent(order=result, customer_id=current_res["customer_id"], old_status=current_status, new_status=target_status))

        return self._sanitize(result)

    async def generate_invoice_pdf(self, order_id: str, user_id: str, is_admin: bool) -> bytes:
        order = await self.repo.get_order_by_id(order_id)
        if not order: raise ResourceNotFound("Order")
            
        if not is_admin and order.get("customer_id") != user_id:
            raise ResourceNotFound("Order")
            
        if order.get("status") not in {"paid", "shipped", "delivered", "refunded"}:
            raise LuviioException("Invoice not available for this order status", "INVALID_STATE", 409)
            
        customer = await self.user_repo.get_user_by_id(order.get("customer_id", "")) or {}
        
        try:
            return await run_in_threadpool(build_invoice_pdf, order, customer)
        except Exception as exc:
            logger.error(f"PDF generation failed: {exc}")
            raise LuviioException("Could not generate invoice", "PDF_ERROR", 500)