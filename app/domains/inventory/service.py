"""
Inventory Service
=================
Path: app/domains/inventory/service.py

Business logic for stock management: reservations, availability, and low-stock alerts.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple
from app.domains.inventory.repository import InventoryRepository
from app.domains.inventory.schemas import (
    StockLevel, ReservationItem, ReservationResult,
    AvailabilityCheck, StockAdjustment
)
from app.domains.inventory.enums import StockStatus
from app.domains.inventory.exceptions import (
    InsufficientStockError, ProductNotFoundError, ReservationFailedError
)
from app.events.bus import get_event_bus, LowStockEvent

logger = logging.getLogger(__name__)


class InventoryService:
    """Service layer for inventory operations."""

    def __init__(self):
        self.repo = InventoryRepository()
        self.event_bus = get_event_bus()

    # ── Availability Checks ───────────────────────────────────────────────────

    async def check_availability(self, product_id: str, quantity: int = 1) -> AvailabilityCheck:
        """
        Check if product is available in requested quantity.

        Consolidates logic from:
        - cart_repo.get_product_stock_status()
        - product_repo.get_product_by_id()

        Returns: AvailabilityCheck with detailed status
        """
        product = await self.repo.get_product_stock_status(product_id)

        if not product:
            return AvailabilityCheck(
                product_id=product_id,
                available=False,
                stock=0,
                is_active=False,
                message="Product not found"
            )

        is_active = product.get("is_active", False)
        stock = product.get("stock", 0)
        available = is_active and stock >= quantity

        message = None
        if not is_active:
            message = "Product is not active"
        elif stock < quantity:
            message = f"Insufficient stock. Available: {stock}, Requested: {quantity}"

        return AvailabilityCheck(
            product_id=product_id,
            available=available,
            stock=stock,
            is_active=is_active,
            message=message
        )

    async def check_multiple_availability(
        self,
        items: List[Tuple[str, int]]
    ) -> Dict[str, AvailabilityCheck]:
        """
        Bulk availability check for multiple products.

        Args:
            items: List of (product_id, quantity) tuples

        Returns: Dict mapping product_id to AvailabilityCheck
        """
        product_ids = [item[0] for item in items]
        products = await self.repo.check_multiple_products_stock(product_ids)

        results = {}
        for product_id, quantity in items:
            product = products.get(product_id)

            if not product:
                results[product_id] = AvailabilityCheck(
                    product_id=product_id,
                    available=False,
                    stock=0,
                    is_active=False,
                    message="Product not found"
                )
                continue

            is_active = product.get("is_active", False)
            stock = product.get("stock", 0)
            available = is_active and stock >= quantity

            message = None
            if not is_active:
                message = "Product is not active"
            elif stock < quantity:
                message = f"Insufficient stock. Available: {stock}, Requested: {quantity}"

            results[product_id] = AvailabilityCheck(
                product_id=product_id,
                available=available,
                stock=stock,
                is_active=is_active,
                message=message
            )

        return results

    # ── Stock Reservations ────────────────────────────────────────────────────

    async def reserve_stock(
        self,
        order_id: str,
        items: List[ReservationItem],
        order_data: Dict[str, Any]
    ) -> ReservationResult:
        """
        Reserve stock for an order at checkout.

        Moved from: payment_repo.create_pending_order_with_reservation()

        This performs an ATOMIC operation:
        1. Create order (status='pending')
        2. Reserve stock (decrement products.stock)
        3. Validate sufficient stock

        Raises: ReservationFailedError if reservation fails
        """
        try:
            # Convert ReservationItem to dict format for RPC
            items_dict = [
                {
                    "product_id": item.product_id,
                    "quantity": item.quantity,
                    "price": item.price
                }
                for item in items
            ]

            # Call atomic RPC
            result = await self.repo.create_pending_order_with_reservation(
                order_data=order_data,
                items=items_dict
            )

            logger.info(
                "[INVENTORY:SERVICE] Stock reserved for order %s (%d items)",
                result.get("id", order_id),
                len(items)
            )

            return ReservationResult(
                success=True,
                order_id=result.get("id", order_id),
                reserved_items=items,
                message="Stock successfully reserved"
            )

        except Exception as exc:
            logger.error(
                "[INVENTORY:SERVICE] Stock reservation failed for order %s: %s",
                order_id,
                exc,
                exc_info=True
            )
            raise ReservationFailedError(order_id, str(exc))

    async def commit_reservation(
        self,
        order_id: str,
        pi_id: str,
        amount: float,
        user_id: str,
        payment_method: Optional[str] = None
    ) -> str:
        """
        Commit stock reservation when payment succeeds.

        Moved from: payment_repo.settle_order_transaction()

        Returns: Settlement status ('SETTLED', 'ALREADY_PAID', 'ORDER_ALREADY_CANCELLED')
        """
        result = await self.repo.settle_order_transaction(
            order_id=order_id,
            pi_id=pi_id,
            amount=amount,
            user_id=user_id,
            payment_method=payment_method
        )

        logger.info(
            "[INVENTORY:SERVICE] Stock reservation committed for order %s: %s",
            order_id,
            result
        )

        return result

    async def release_reservation(self, order_id: str, reason: str = "order_cancelled") -> bool:
        """
        Release reserved stock (cancellation/abandonment).

        Consolidates:
        - payment_repo.release_abandoned_order() (automated cron)
        - order_repo.cancel_order_and_restore_stock() (manual)

        Returns: True if stock was released successfully
        """
        result = await self.repo.release_abandoned_order(order_id, reason)

        success = result in ("CANCELLED", "ALREADY_CANCELLED")

        if success:
            logger.info(
                "[INVENTORY:SERVICE] Stock released for order %s (reason: %s)",
                order_id,
                reason
            )
        else:
            logger.error(
                "[INVENTORY:SERVICE] Failed to release stock for order %s: %s",
                order_id,
                result
            )

        return success

    async def cancel_order_with_stock_restoration(
        self,
        order_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Cancel order and restore stock (manual cancellation with guards).

        Moved from: order_repo.cancel_order_and_restore_stock()

        Guards against cancelling already-fulfilled orders.

        Returns: Updated order if cancelled, None if rejected
        """
        result = await self.repo.cancel_order_and_restore_stock(order_id, user_id)

        if result:
            logger.info(
                "[INVENTORY:SERVICE] Order %s cancelled by %s, stock restored",
                order_id,
                "customer" if user_id else "admin"
            )
        else:
            logger.warning(
                "[INVENTORY:SERVICE] Order %s cancellation rejected (already fulfilled or not found)",
                order_id
            )

        return result

    # ── Stock Levels ──────────────────────────────────────────────────────────

    async def get_stock_level(self, product_id: str) -> Optional[StockLevel]:
        """
        Get current stock level with low-stock status.

        New function: Unified stock level query with status calculation.
        """
        product = await self.repo.get_product_by_id(product_id)

        if not product:
            return None

        stock = product.get("stock", 0)
        threshold = product.get("low_stock_threshold", 10)

        return StockLevel(
            product_id=product_id,
            stock=stock,
            low_stock_threshold=threshold,
            is_low_stock=(0 < stock <= threshold),
            is_out_of_stock=(stock == 0)
        )

    # ── Low Stock Alerts ──────────────────────────────────────────────────────

    async def check_and_publish_low_stock_alerts(self) -> int:
        """
        Check for low-stock products and publish LowStockEvent.

        🔥 NEW: This event publisher is currently MISSING from the codebase.
        The handler exists (order_handlers.py:152) but is never triggered.

        Should be called:
        - After stock adjustments
        - By scheduled cron job

        Returns: Number of alerts published
        """
        low_stock_products = await self.repo.get_low_stock_products()

        alerts_sent = 0
        for product in low_stock_products:
            try:
                event = LowStockEvent(
                    product_id=product["id"],
                    product_name=product.get("name", "Unknown"),
                    stock=product.get("stock", 0),
                    threshold=product.get("low_stock_threshold", 10)
                )

                self.event_bus.publish(event)
                alerts_sent += 1

                logger.info(
                    "[INVENTORY:SERVICE] Low stock alert published for product %s (%s): %d/%d",
                    product["id"],
                    product.get("name"),
                    product.get("stock"),
                    product.get("low_stock_threshold")
                )

            except Exception as exc:
                logger.error(
                    "[INVENTORY:SERVICE] Failed to publish low stock alert for %s: %s",
                    product["id"],
                    exc
                )

        if alerts_sent > 0:
            logger.info("[INVENTORY:SERVICE] Published %d low stock alerts", alerts_sent)

        return alerts_sent

    # ── Abandoned Order Cleanup ───────────────────────────────────────────────

    async def release_stale_pending_orders(self, minutes_old: int = 30) -> int:
        """
        Release stock for abandoned pending orders (cron job).

        New function: Consolidates abandoned-checkout cleanup logic.

        Returns: Number of orders processed
        """
        stale_orders = await self.repo.list_stale_pending_orders(minutes_old)

        released_count = 0
        for order in stale_orders:
            try:
                order_id = order.get("id")
                success = await self.release_reservation(
                    order_id,
                    reason="payment_timeout"
                )

                if success:
                    released_count += 1

            except Exception as exc:
                logger.error(
                    "[INVENTORY:SERVICE] Failed to release stale order %s: %s",
                    order.get("id"),
                    exc
                )

        if released_count > 0:
            logger.info(
                "[INVENTORY:SERVICE] Released stock for %d/%d stale orders",
                released_count,
                len(stale_orders)
            )

        return released_count
