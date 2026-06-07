"""
Order Repository
================
Path: app/repositories/order_repo.py
"""
import logging
from typing import Any
from .base import BaseRepository

logger = logging.getLogger(__name__)

ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

class OrderRepository(BaseRepository):
    def get_order_by_idempotency_key(self, user_id: str, key: str) -> dict[str, Any] | None:
        """Check if an order was already created with this key."""
        res = (
            self.admin_sb.table("orders")
            .select(ORDER_ITEMS_SELECT)
            .eq("customer_id", user_id)
            .eq("idempotency_key", key)
            .maybe_single()
            .execute()
        )
        return res.data if res and hasattr(res, "data") else None

    def get_order_by_id(self, order_id: str, user_id: str = None) -> dict[str, Any] | None:
        """Fetch full order details. Optional user_id for customer verification."""
        q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("id", order_id)
        if user_id:
            q = q.eq("customer_id", user_id)
        res = q.maybe_single().execute()
        return res.data if res and hasattr(res, "data") else None

    def create_order_with_items(self, order_data: dict, order_items: list) -> dict[str, Any]:
        """Insert order and its items."""
        # 1. Insert Order
        order_res = self.admin_sb.table("orders").insert(order_data).execute()
        order = order_res.data[0]
        
        # 2. Assign Order ID to items and Insert
        for item in order_items:
            item["order_id"] = order["id"]
        self.admin_sb.table("order_items").insert(order_items).execute()
        
        return order

    def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> dict[str, Any] | None:
        """Optimistic Locking: Update order ONLY if it is still in the expected status."""
        res = (
            self.admin_sb.table("orders")
            .update(updates)
            .eq("id", order_id)
            .eq("status", expected_status)
            .execute()
        )
        return res.data[0] if res and hasattr(res, "data") and res.data else None