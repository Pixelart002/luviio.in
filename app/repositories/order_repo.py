"""
Order Repository
================
Path: app/repositories/order_repo.py
"""
import logging
from typing import Any
from postgrest.exceptions import APIError as PostgrestError
from .base import BaseRepository

logger = logging.getLogger(__name__)

ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

class OrderRepository(BaseRepository):
    
    async def get_pricing_config(self) -> dict[str, Any]:
        try:
            res = self.admin_sb.table("pricing_config").select("*").limit(1).single().execute()
            return res.data if res and res.data else {}
        except Exception:
            return {}

    async def get_shipping_address(self, address_id: str, user_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
        return res.data

    async def get_active_products(self, product_ids: list[str]) -> list[dict[str, Any]]:
        res = self.admin_sb.table("products").select("*").in_("id", product_ids).eq("is_active", True).execute()
        return res.data or []

    async def get_order_by_idempotency_key(self, user_id: str, key: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("customer_id", user_id).eq("idempotency_key", key).maybe_single().execute()
        return res.data if res and hasattr(res, "data") else None

    async def get_order_by_id(self, order_id: str, user_id: str = None) -> dict[str, Any] | None:
        q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("id", order_id)
        if user_id: q = q.eq("customer_id", user_id)
        res = q.maybe_single().execute()
        return res.data if res and hasattr(res, "data") else None

    async def create_order_with_items(self, order_data: dict, order_items: list) -> dict[str, Any]:
        # 1. Insert Order
        order_res = self.admin_sb.table("orders").insert(order_data).execute()
        order = order_res.data[0]
        
        # 2. Assign Order ID to items and Insert
        for item in order_items: item["order_id"] = order["id"]
        self.admin_sb.table("order_items").insert(order_items).execute()
        
        return order

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("orders").update(updates).eq("id", order_id).eq("status", expected_status).execute()
        return res.data[0] if res and hasattr(res, "data") and res.data else None

    async def get_user_orders(self, user_id: str, status_filter: str | None, page: int, page_size: int) -> tuple[list, int]:
        offset = (page - 1) * page_size
        q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
        if status_filter: q = q.eq("status", status_filter)
        res = q.range(offset, offset + page_size - 1).execute()
        return res.data or [], res.count or 0

    async def get_all_orders(self, status_filter: str | None, page: int, page_size: int) -> tuple[list, int]:
        offset = (page - 1) * page_size
        q = self.admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
        if status_filter: q = q.eq("status", status_filter)
        res = q.range(offset, offset + page_size - 1).execute()
        return res.data or [], res.count or 0

    async def get_order_for_admin_update(self, order_id: str) -> dict[str, Any] | None:
        res = self.admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
        return res.data

    async def get_user_email(self, user_id: str) -> str | None:
        res = self.admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
        return res.data["email"] if res and res.data else None