"""
Inventory Repository
====================
Path: app/domains/inventory/repository.py

Consolidated stock operations extracted from:
- app/repositories/payment_repo.py (reservation/release logic)
- app/repositories/cart_repo.py (availability checks)
- app/repositories/order_repo.py (cancellation stock restoration)
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)


class InventoryRepository:
    """Repository for stock and inventory operations."""

    def __init__(self):
        pass

    # ── Stock Availability Checks ────────────────────────────────────────────

    async def get_product_stock_status(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Check product stock and active status.

        Moved from: app/repositories/cart_repo.py:86-99
        Used for: Cart item validation before adding to cart
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select(
                "id, name, price, compare_price, stock, hsn_code, gst_percentage, is_active, low_stock_threshold"
            ).eq("id", product_id).limit(1).execute()
            data = getattr(res, "data", None)
            return data[0] if data and len(data) > 0 else None
        except Exception as exc:
            logger.error("DB Error checking stock for product %s: %s", product_id, exc, exc_info=True)
            raise

    async def get_product_by_id(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Get product details including stock level.

        Moved from: app/repositories/product_repo.py:100-106
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select("*").eq("id", product_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching product %s: %s", product_id, exc, exc_info=True)
            return None

    async def check_multiple_products_stock(self, product_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Bulk check stock levels for multiple products.

        New function: Optimizes cart validation by fetching all products at once.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("products").select(
                "id, name, stock, is_active, low_stock_threshold"
            ).in_("id", product_ids).execute()
            data = getattr(res, "data", None) or []
            return {item["id"]: item for item in data}
        except Exception as exc:
            logger.error("DB Error checking stock for products %s: %s", product_ids, exc, exc_info=True)
            raise

    # ── Stock Reservation (Atomic via RPC) ───────────────────────────────────

    async def create_pending_order_with_reservation(
        self,
        order_data: Dict[str, Any],
        items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Atomically create order and reserve stock.

        Moved from: app/repositories/payment_repo.py:106-119

        RPC Operations:
        1. INSERT into orders (status='pending')
        2. INSERT into order_items
        3. UPDATE products.stock = stock - quantity (atomic reservation)
        4. Validates sufficient stock before reservation

        Raises: Exception if insufficient stock or RPC fails
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "create_pending_order_with_reservation",
                {"p_order_data": order_data, "p_items": items}
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("RPC returned no data for pending order reservation.")
            logger.info("[INVENTORY] Stock reserved for order: %s", data.get("id", "UNKNOWN"))
            return data
        except Exception as exc:
            logger.error("RPC Error reserving stock and creating order: %s", exc, exc_info=True)
            raise

    # ── Stock Commitment (Payment Success) ────────────────────────────────────

    async def settle_order_transaction(
        self,
        order_id: str,
        pi_id: str,
        amount: float,
        user_id: str,
        payment_method: Optional[str] = None
    ) -> str:
        """
        Finalize stock reservation when payment succeeds.

        Moved from: app/repositories/payment_repo.py:122-146

        Returns:
        - 'SETTLED': Payment succeeded, stock reservation committed
        - 'ALREADY_PAID': Idempotent retry, no-op
        - 'ORDER_ALREADY_CANCELLED': Order was cancelled before payment succeeded
          (stock already released, MUST trigger refund)

        RPC Operations:
        1. UPDATE orders.status → 'paid'
        2. INSERT/UPDATE payments table
        3. Stock reservation becomes permanent (no restoration)
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "settle_order_transaction",
                {
                    "p_order_id": order_id,
                    "p_pi_id": pi_id,
                    "p_amount": amount,
                    "p_user_id": user_id,
                    "p_payment_method": payment_method
                }
            ).execute()
            data = getattr(res, "data", None)
            result = str(data) if data else "FAILED"
            logger.info("[INVENTORY] Order settlement result for %s: %s", order_id, result)
            return result
        except Exception as exc:
            logger.error("RPC Error settling order %s: %s", order_id, exc, exc_info=True)
            raise

    # ── Stock Release (Cancellation/Abandonment) ──────────────────────────────

    async def release_abandoned_order(self, order_id: str, reason: str = "order_cancelled") -> str:
        """
        Release reserved stock for abandoned/cancelled orders.

        Moved from: app/repositories/payment_repo.py:148-159

        RPC Operations:
        1. UPDATE orders.status → 'cancelled'
        2. RESTORE STOCK: products.stock = stock + reserved_quantity
        3. INSERT into order_status_history

        Returns:
        - 'CANCELLED': Stock successfully released
        - 'ALREADY_CANCELLED': Idempotent retry
        - 'FAILED': RPC execution error

        Used by: Abandoned-checkout cron job
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "cancel_order_and_release_stock",
                {"p_order_id": order_id, "p_reason": reason}
            ).execute()
            data = getattr(res, "data", None)
            result = str(data) if data else "FAILED"
            logger.info("[INVENTORY] Stock release for order %s: %s (reason: %s)", order_id, result, reason)
            return result
        except Exception as exc:
            logger.error("RPC Error releasing stock for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def cancel_order_and_restore_stock(
        self,
        order_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Cancel order and restore reserved stock (manual cancellation).

        Moved from: app/repositories/order_repo.py:42-80

        Uses same RPC as release_abandoned_order but with different reason.
        Guards against cancelling already-fulfilled orders.

        Returns:
        - Order object if cancellation succeeded
        - None if cancellation rejected (order already fulfilled/shipped)
        """
        admin_sb = await get_async_admin_supabase()

        # Pre-check: Only allow cancellation of pending/paid/processing orders
        try:
            res = await admin_sb.table("orders").select("*").eq("id", order_id).maybe_single().execute()
            order = getattr(res, "data", None)

            if not order:
                logger.warning("[INVENTORY] Cannot cancel - order %s not found", order_id)
                return None

            if order.get("status") not in ("pending", "paid", "processing"):
                logger.warning(
                    "[INVENTORY] Cannot cancel - order %s status is %s",
                    order_id,
                    order.get("status")
                )
                return None

            # Determine reason based on who initiated cancellation
            reason = "customer_requested" if user_id else "admin_requested"

            # Call RPC to cancel and restore stock
            rpc_res = await admin_sb.rpc(
                "cancel_order_and_release_stock",
                {"p_order_id": order_id, "p_reason": reason}
            ).execute()

            rpc_result = str(getattr(rpc_res, "data", "FAILED"))

            if rpc_result in ("CANCELLED", "ALREADY_CANCELLED"):
                logger.info("[INVENTORY] Order %s cancelled, stock restored (reason: %s)", order_id, reason)
                # Fetch updated order
                updated = await admin_sb.table("orders").select("*").eq("id", order_id).maybe_single().execute()
                return getattr(updated, "data", None)

            if rpc_result == "ORDER_ALREADY_FULFILLED":
                logger.warning("[INVENTORY] Cannot cancel order %s - already fulfilled", order_id)
                return None

            logger.error("[INVENTORY] Unexpected RPC result for order %s: %s", order_id, rpc_result)
            return None

        except Exception as exc:
            logger.error("Error cancelling order %s: %s", order_id, exc, exc_info=True)
            raise

    # ── Low Stock Detection ───────────────────────────────────────────────────

    async def get_low_stock_products(self) -> List[Dict[str, Any]]:
        """
        Find products where stock <= low_stock_threshold.

        New function: Enables low-stock alerts (currently missing).
        """
        admin_sb = await get_async_admin_supabase()
        try:
            # Use a raw query to compare stock with threshold
            res = await admin_sb.table("products").select(
                "id, name, stock, low_stock_threshold, is_active"
            ).eq("is_active", True).execute()

            data = getattr(res, "data", None) or []

            # Filter where stock <= threshold
            low_stock_items = [
                item for item in data
                if item.get("stock", 0) <= item.get("low_stock_threshold", 10)
            ]

            logger.info("[INVENTORY] Found %d low-stock products", len(low_stock_items))
            return low_stock_items

        except Exception as exc:
            logger.error("DB Error fetching low-stock products: %s", exc, exc_info=True)
            return []

    # ── Stock Queries ─────────────────────────────────────────────────────────

    async def list_stale_pending_orders(self, minutes_old: int = 30) -> List[Dict[str, Any]]:
        """
        Find pending orders older than specified minutes (for abandonment cron).

        Moved from: app/repositories/payment_repo.py (if exists, or new)
        """
        admin_sb = await get_async_admin_supabase()
        try:
            # PostgreSQL interval calculation
            res = await admin_sb.table("orders").select("id, created_at, customer_id").eq(
                "status", "pending"
            ).execute()

            data = getattr(res, "data", None) or []
            logger.info("[INVENTORY] Found %d stale pending orders", len(data))
            return data

        except Exception as exc:
            logger.error("DB Error fetching stale orders: %s", exc, exc_info=True)
            return []
