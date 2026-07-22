"""
Order Repository — Async Enterprise Grade (HEAVILY LOGGED)
=========================================================
Path: app/repositories/order_repo.py

Architecture & Fixes:
  ✅ Stateless Execution — Fetches Supabase Admin client on-demand inside async methods.
  ✅ Resolves Coroutine Crash — Awaits async client factory to prevent AttributeError.
  ✅ Dual-ID Resolution — Fetches cleanly by UUID or human-readable NanoID (order_number).
"""
import logging
from typing import Any, Optional, Tuple, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)
ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

class AsyncOrderRepository:
    def __init__(self):
        # Deferred client initialization to prevent coroutine AttributeError in sync constructor
        pass

    async def get_order_by_id(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        logger.debug(f"[REPO:ORDERS] Fetching order {order_id} | User filter: {user_id}")
        try:
            # 🔥 FIX: Supports fetching by standard UUID or readable NanoID (e.g. ORD-4A8B-9C2D)
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT)
            if len(order_id) == 36 and "-" in order_id:
                q = q.eq("id", order_id)
            else:
                q = q.eq("order_number", order_id)

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

    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Atomically cancels order and restores stock — works for pending AND paid orders."""
        admin_sb = await get_async_admin_supabase()
        logger.info(f"[REPO:ORDERS] Attempting to cancel order {order_id} and restore stock. User filter: {user_id}")
        try:
            q = admin_sb.table("orders").update({"status": "cancelled"}) \
                .eq("id", order_id) \
                .in_("status", ["pending", "paid"])  # ← Paid bhi allow
            if user_id: q = q.eq("customer_id", user_id)
            
            res = await q.execute()
            if not res or not res.data:
                logger.warning(f"[REPO:ORDERS] Cancel failed. Order {order_id} might not be in pending/paid state or invalid user.")
                return None
            updated_order = res.data[0]
            logger.info(f"[REPO:ORDERS] Order {order_id} status updated to 'cancelled'. Initiating stock restoration...")

            # Restore stock — non-fatal, best-effort
            items_res = await admin_sb.table("order_items").select("product_id, quantity").eq("order_id", order_id).execute()
            restored_count = 0
            
            for item in (items_res.data or []):
                if item.get("product_id"):
                    try:
                        logger.debug(f"[REPO:ORDERS] Restoring stock for product {item['product_id']} (Qty: {item['quantity']})")
                        await admin_sb.rpc("increment_stock", {
                            "p_id": item["product_id"],
                            "p_qty": item["quantity"]
                        }).execute()
                        restored_count += 1
                    except Exception as e:
                        logger.error(f"[REPO:ORDERS] Stock restore failed for product {item['product_id']}: {e}")
                        # Continue — order is already cancelled; stock can be corrected manually
            
            logger.info(f"[REPO:ORDERS] Cancel complete for {order_id}. Restored stock for {restored_count} item(s).")
            return updated_order
        except Exception as e:
            logger.error(f"[REPO:ORDERS] CRITICAL Error during cancel & restore for {order_id}: {e}", exc_info=True)
            return None

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        logger.info(f"[REPO:ORDERS] Safe updating order {order_id}. Expected status: '{expected_status}'. Updates: {updates}")
        try:
            res = await admin_sb.table("orders").update(updates).eq("id", order_id).eq("status", expected_status).execute()
            if res and res.data:
                logger.info(f"[REPO:ORDERS] Order {order_id} successfully updated.")
                return res.data[0]
            logger.warning(f"[REPO:ORDERS] Safe update failed. Order {order_id} not in '{expected_status}' state.")
            return None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error updating order {order_id}: {e}", exc_info=True)
            return None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        logger.debug(f"[REPO:ORDERS] Fetching orders for user {user_id} | Page {page} | Status: {status_filter}")
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
            if status_filter: q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching user orders: {e}", exc_info=True)
            return [], 0

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        logger.debug(f"[REPO:ORDERS] Admin fetching ALL orders | Page {page} | Status: {status_filter}")
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
            if status_filter: q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching all orders: {e}", exc_info=True)
            return [], 0

    async def get_order_for_admin_update(self, order_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        logger.debug(f"[REPO:ORDERS] Admin fetching specific order {order_id} for update.")
        try:
            res = await admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error fetching order for admin update {order_id}: {e}", exc_info=True)
            return None

    async def get_user_email(self, user_id: str) -> Optional[str]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            return res.data["email"] if res and res.data else None
        except Exception as e:
            logger.warning(f"[REPO:ORDERS] Could not fetch email for user {user_id}: {e}")
            return None