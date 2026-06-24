"""
Order Repository — Async Enterprise Grade (HEAVILY LOGGED & ACID COMPLIANT)
=========================================================================
Path: app/repositories/order_repo.py

🔥 BUG FIXED: Replaced brittle Python-side loop and missing 'increment_stock' 
   RPC with a 100% atomic 'admin_cancel_and_restore' PostgreSQL transaction.
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
        logger.debug(f"[REPO:ORDERS] Fetching order {order_id} | User filter: {user_id}")
        try:
            q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("id", order_id)
            if user_id: q = q.eq("customer_id", user_id)
            res = await q.maybe_single().execute()
            
            if res and res.data:
                logger.info(f"[REPO:ORDERS] Order {order_id} fetched successfully.")
            else:
                logger.warning(f"[REPO:ORDERS] Order {order_id} not found or access denied.")
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed to fetch order {order_id}: {e}", exc_info=True)
            return None

    # 🔥 FIX: Completely rewritten to use the Atomic RPC Transaction
    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Atomically cancels order and restores stock natively inside Postgres."""
        logger.info(f"[REPO:ORDERS] Attempting to cancel order {order_id} atomically. User filter: {user_id}")
        try:
            # Send it to our new FAANG-grade database transaction
            res = await self.admin_sb.rpc("admin_cancel_and_restore", {
                "p_order_id": order_id,
                "p_user_id": user_id
            }).execute()
            
            updated_order = getattr(res, "data", None)
            
            if not updated_order:
                logger.warning(f"[REPO:ORDERS] Cancel failed. Order {order_id} not found, denied, or not in pending/paid state.")
                return None
                
            logger.info(f"[REPO:ORDERS] Cancel complete for {order_id}. Stock restored atomically in DB.")
            return updated_order
        except Exception as e:
            logger.error(f"[REPO:ORDERS] CRITICAL Error during atomic cancel & restore for {order_id}: {e}", exc_info=True)
            return None

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> Optional[dict[str, Any]]:
        logger.info(f"[REPO:ORDERS] Safe updating order {order_id}. Expected status: '{expected_status}'. Updates: {updates}")
        try:
            res = await self.admin_sb.table("orders").update(updates).eq("id", order_id).eq("status", expected_status).execute()
            if res and res.data:
                logger.info(f"[REPO:ORDERS] Order {order_id} successfully updated.")
                return res.data[0]
            logger.warning(f"[REPO:ORDERS] Safe update failed. Order {order_id} not in '{expected_status}' state.")
            return None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error updating order {order_id}: {e}", exc_info=True)
            return None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        logger.debug(f"[REPO:ORDERS] Fetching orders for user {user_id} | Page {page} | Status: {status_filter}")
        offset = (page - 1) * page_size
        try:
            q = self.admin_sb.table("orders").select(ORDER_ITEMS_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
            if status_filter: q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching user orders: {e}", exc_info=True)
            return [], 0

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        logger.debug(f"[REPO:ORDERS] Admin fetching ALL orders | Page {page} | Status: {status_filter}")
        offset = (page - 1) * page_size
        try:
            q = self.admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
            if status_filter: q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching all orders: {e}", exc_info=True)
            return [], 0

    async def get_order_for_admin_update(self, order_id: str) -> Optional[dict[str, Any]]:
        logger.debug(f"[REPO:ORDERS] Admin fetching specific order {order_id} for update.")
        try:
            res = await self.admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error fetching order for admin update {order_id}: {e}", exc_info=True)
            return None

    async def get_user_email(self, user_id: str) -> Optional[str]:
        try:
            res = await self.admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            return res.data["email"] if res and res.data else None
        except Exception as e:
            logger.warning(f"[REPO:ORDERS] Could not fetch email for user {user_id}: {e}")
            return None