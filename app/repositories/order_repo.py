"""
Order Repository — Async Enterprise Grade
=========================================
Path: app/repositories/order_repo.py
"""
import logging
from typing import Any, Optional, Tuple, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)
ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

class AsyncOrderRepository:
    def __init__(self):
        self.admin_sb = get_async_admin_supabase()

    async def get_order_by_id(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("id", order_id)
        if user_id: q = q.eq("customer_id", user_id)
        res = await q.maybe_single().execute()
        return res.data

    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Atomically cancels order and restores stock — works for pending AND paid orders."""
        q = self.admin_sb.table("orders").update({"status": "cancelled"}) \
            .eq("id", order_id) \
            .in_("status", ["pending", "paid"])  # ← Paid bhi allow
        if user_id: q = q.eq("customer_id", user_id)
        
        res = await q.execute()
        if not res or not res.data:
            return None
        updated_order = res.data[0]

        # Restore stock — non‑fatal, best‑effort
        items_res = await self.admin_sb.table("order_items").select("product_id, quantity").eq("order_id", order_id).execute()
        for item in (items_res.data or []):
            if item.get("product_id"):
                try:
                    await self.admin_sb.rpc("increment_stock", {
                        "p_id": item["product_id"],
                        "p_qty": item["quantity"]
                    }).execute()
                except Exception as e:
                    logger.error(f"Stock restore failed for product {item['product_id']}: {e}")
                    # Continue — order is already cancelled; stock can be corrected manually
        
        return updated_order

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> Optional[dict[str, Any]]:
        res = await self.admin_sb.table("orders").update(updates).eq("id", order_id).eq("status", expected_status).execute()
        return res.data[0] if res and res.data else None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        offset = (page - 1) * page_size
        q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
        if status_filter: q = q.eq("status", status_filter)
        res = await q.range(offset, offset + page_size - 1).execute()
        return res.data or [], res.count or 0

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        offset = (page - 1) * page_size
        q = self.admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
        if status_filter: q = q.eq("status", status_filter)
        res = await q.range(offset, offset + page_size - 1).execute()
        return res.data or [], res.count or 0

    async def get_order_for_admin_update(self, order_id: str) -> Optional[dict[str, Any]]:
        res = await self.admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
        return res.data

    async def get_user_email(self, user_id: str) -> Optional[str]:
        res = await self.admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
        return res.data["email"] if res and res.data else None