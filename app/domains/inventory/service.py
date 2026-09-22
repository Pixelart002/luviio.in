"""
Inventory Service
=================
Business logic for stock management: reservations, availability, adjustments,
receiving, returns, damage, wastage, reconciliation, and low-stock alerts.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.domains.inventory.exceptions import ReservationFailedError
from app.domains.inventory.repository import InventoryRepository
from app.domains.inventory.schemas import (
    AvailabilityCheck,
    InventoryOperationRequest,
    InventoryOperationResult,
    InventoryReconcileRequest,
    ReservationItem,
    ReservationResult,
    StockLevel,
)
from app.events.bus import LowStockEvent, get_event_bus

logger = logging.getLogger(__name__)


class InventoryService:
    """Service layer for stock and inventory operations."""

    def __init__(self):
        self.repo = InventoryRepository()
        self.event_bus = get_event_bus()

    @staticmethod
    def _require_positive_quantity(quantity: int, field_name: str = "quantity") -> None:
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError(f"{field_name} must be a positive integer")

    @staticmethod
    def _require_non_negative_stock(quantity: int, field_name: str = "counted_stock") -> None:
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")

    async def check_availability(self, product_id: str, quantity: int = 1) -> AvailabilityCheck:
        self._require_positive_quantity(quantity)
        product = await self.repo.get_product_stock_status(product_id)
        if not product:
            return AvailabilityCheck(product_id=product_id, available=False, stock=0, is_active=False, message="Product not found")
        is_active = product.get("is_active", False)
        stock = product.get("stock", 0)
        available = is_active and stock >= quantity
        message = None
        if not is_active:
            message = "Product is not active"
        elif stock < quantity:
            message = f"Insufficient stock. Available: {stock}, Requested: {quantity}"
        return AvailabilityCheck(product_id=product_id, available=available, stock=stock, is_active=is_active, message=message)

    async def check_multiple_availability(self, items: List[Tuple[str, int]]) -> Dict[str, AvailabilityCheck]:
        for _, quantity in items:
            self._require_positive_quantity(quantity)
        product_ids = [item[0] for item in items]
        products = await self.repo.check_multiple_products_stock(product_ids)
        results = {}
        for product_id, quantity in items:
            product = products.get(product_id)
            if not product:
                results[product_id] = AvailabilityCheck(product_id=product_id, available=False, stock=0, is_active=False, message="Product not found")
                continue
            is_active = product.get("is_active", False)
            stock = product.get("stock", 0)
            available = is_active and stock >= quantity
            message = None if available else ("Product is not active" if not is_active else f"Insufficient stock. Available: {stock}, Requested: {quantity}")
            results[product_id] = AvailabilityCheck(product_id=product_id, available=available, stock=stock, is_active=is_active, message=message)
        return results

    async def reserve_stock(self, order_id: str, items: List[ReservationItem], order_data: Dict[str, Any]) -> ReservationResult:
        if not items:
            raise ValueError("At least one reservation item is required")
        for item in items:
            self._require_positive_quantity(item.quantity, "reservation quantity")
        try:
            items_dict = [{"product_id": item.product_id, "quantity": item.quantity, "price": item.price} for item in items]
            result = await self.repo.create_pending_order_with_reservation(order_data=order_data, items=items_dict)
            return ReservationResult(success=True, order_id=result.get("id", order_id), reserved_items=items, message="Stock successfully reserved")
        except Exception as exc:
            logger.error("Stock reservation failed for order %s: %s", order_id, exc, exc_info=True)
            raise ReservationFailedError(order_id, str(exc))

    async def commit_reservation(self, order_id: str, pi_id: str, amount: float, user_id: str, payment_method: Optional[str] = None, stripe_currency: Optional[str] = None) -> str:
        if not stripe_currency:
            raise ValueError("Verified Stripe currency is required for reservation settlement")
        return await self.repo.settle_order_transaction(order_id=order_id, pi_id=pi_id, amount=amount, user_id=user_id, payment_method=payment_method, stripe_currency=stripe_currency)

    async def release_reservation(self, order_id: str, reason: str = "order_cancelled") -> bool:
        result = await self.repo.release_abandoned_order(order_id, reason)
        return result in ("CANCELLED", "ALREADY_CANCELLED")

    async def cancel_order_with_stock_restoration(self, order_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        return await self.repo.cancel_order_and_restore_stock(order_id, user_id)

    async def get_stock_level(self, product_id: str) -> Optional[StockLevel]:
        product = await self.repo.get_product_by_id(product_id)
        if not product:
            return None
        stock = product.get("stock", 0)
        threshold = product.get("low_stock_threshold", 10)
        return StockLevel(product_id=product_id, stock=stock, low_stock_threshold=threshold, is_low_stock=(0 < stock <= threshold), is_out_of_stock=(stock == 0))

    async def adjust_stock(self, product_id: str, delta: int, reason: str) -> Dict[str, Any]:
        if not isinstance(delta, int) or isinstance(delta, bool) or delta == 0:
            raise ValueError("delta must be a non-zero integer")
        return await self.repo.admin_adjust_stock(product_id, delta, reason)

    async def receive_stock(self, payload: InventoryOperationRequest) -> InventoryOperationResult:
        self._require_positive_quantity(payload.quantity)
        result = await self.repo.inventory_receive_stock(payload.product_id, payload.quantity, payload.reason, payload.reference_id, payload.metadata)
        return InventoryOperationResult(**self._normalize_operation_result(result))

    async def record_return(self, payload: InventoryOperationRequest) -> InventoryOperationResult:
        self._require_positive_quantity(payload.quantity)
        result = await self.repo.inventory_record_return(payload.product_id, payload.quantity, payload.reason, payload.order_id, payload.metadata)
        return InventoryOperationResult(**self._normalize_operation_result(result))

    async def record_damage(self, payload: InventoryOperationRequest) -> InventoryOperationResult:
        self._require_positive_quantity(payload.quantity)
        result = await self.repo.inventory_record_damage(payload.product_id, payload.quantity, payload.reason, payload.reference_id, payload.metadata)
        return InventoryOperationResult(**self._normalize_operation_result(result))

    async def record_wastage(self, payload: InventoryOperationRequest) -> InventoryOperationResult:
        self._require_positive_quantity(payload.quantity)
        result = await self.repo.inventory_record_wastage(payload.product_id, payload.quantity, payload.reason, payload.reference_id, payload.metadata)
        return InventoryOperationResult(**self._normalize_operation_result(result))

    async def reconcile_stock(self, payload: InventoryReconcileRequest) -> InventoryOperationResult:
        self._require_non_negative_stock(payload.counted_stock)
        result = await self.repo.inventory_reconcile_stock(payload.product_id, payload.counted_stock, payload.reason, payload.metadata)
        return InventoryOperationResult(**self._normalize_operation_result(result))

    async def list_history(self, product_id: str, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        return await self.repo.list_inventory_history(product_id, limit, offset)

    async def get_summary(self, low_stock_only: bool = False) -> List[Dict[str, Any]]:
        return await self.repo.get_inventory_summary(low_stock_only)

    @staticmethod
    def _normalize_operation_result(result: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "product_id": result.get("product_id"),
            "previous_stock": result.get("previous_stock", result.get("old_stock", result.get("stock_before", 0))),
            "new_stock": result.get("new_stock", result.get("stock_after", 0)),
            "delta": result.get("delta", result.get("quantity_delta", 0)),
            "activity_id": result.get("activity_id") or result.get("id"),
        }

    async def check_and_publish_low_stock_alerts(self) -> int:
        low_stock_products = await self.repo.get_low_stock_products()
        alerts_sent = 0
        for product in low_stock_products:
            try:
                self.event_bus.publish(LowStockEvent(product_id=product["id"], product_name=product.get("name", "Unknown"), stock=product.get("stock", 0), threshold=product.get("low_stock_threshold", 10)))
                alerts_sent += 1
            except Exception as exc:
                logger.error("Failed to publish low stock alert for %s: %s", product["id"], exc, exc_info=True)
        return alerts_sent

    async def release_stale_pending_orders(self, minutes_old: int = 30) -> int:
        stale_orders = await self.repo.list_stale_pending_orders(minutes_old)
        released_count = 0
        for order in stale_orders:
            try:
                if await self.release_reservation(order.get("id"), reason="payment_timeout"):
                    released_count += 1
            except Exception as exc:
                logger.error("Failed to release stale order %s: %s", order.get("id"), exc, exc_info=True)
        return released_count
