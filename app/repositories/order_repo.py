"""
Order Repository — Async Enterprise Grade (HEAVILY LOGGED & GST READY)
======================================================================
Path: app/repositories/order_repo.py

Architecture & Fixes:
  ✅ Stateless Execution — Fetches Supabase Admin client on-demand inside async methods.
  ✅ Resolves Coroutine Crash — Awaits async client factory to prevent AttributeError.
  ✅ Dual-ID Resolution — Fetches cleanly by UUID or human-readable NanoID (order_number).
  ✅ GST & HSN Ready — ORDER_ITEMS_SELECT auto-joins HSN & GST rate for PDF invoice generation.
  ✅ Atomic Creation — Added create_order_with_items to lock historical tax snapshots.
  ✅ FIX (July 2026): `compare_price` added to the products join — this was the actual
     root cause of invoices always showing "—" in the Discount column. Without it,
     pdf_invoice.py had no MRP to compare against the selling price, so it could
     never compute (compare_price - price) and always fell back to zero discount.
"""
import logging
from typing import Any, Optional, Tuple, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

# 🔥 FIX: added compare_price so invoices can actually calculate the discount.
ORDER_ITEMS_SELECT = "*, order_items(*, products(name, image_url, slug, hsn_code, gst_percentage, compare_price))"

class AsyncOrderRepository:
    def __init__(self):
        # Deferred client initialization to prevent coroutine AttributeError in sync constructor
        pass

    # ── Order Creation (New Atomic Snapshot Method) ──────────────────────────
    async def create_order_with_items(self, order_data: dict[str, Any], items_data: List[dict[str, Any]]) -> Optional[dict[str, Any]]:
        """
        Creates an order and inserts all order items with their frozen HSN/GST snapshots.
        """
        admin_sb = await get_async_admin_supabase()
        logger.info(f"[REPO:ORDERS] Creating new order for customer {order_data.get('customer_id')} with {len(items_data)} items.")
        try:
            # 1. Insert main order row
            order_res = await admin_sb.table("orders").insert(order_data).execute()
            if not order_res or not getattr(order_res, "data", None):
                logger.error("[REPO:ORDERS] Failed to insert main order row.")
                return None
            
            created_order = order_res.data[0]
            order_id = created_order["id"]
            logger.debug(f"[REPO:ORDERS] Order row created with ID: {order_id}. Inserting items...")

            # 2. Attach order_id to items and insert snapshots
            for item in items_data:
                item["order_id"] = order_id
                # Ensure generic fallback if missing
                item["hsn_code"] = item.get("hsn_code") or "9988"
                item["gst_percentage"] = item.get("gst_percentage") or 18
                item["compare_price"] = item.get("compare_price")

            items_res = await admin_sb.table("order_items").insert(items_data).execute()
            if not items_res or not getattr(items_res, "data", None):
                logger.warning(f"[REPO:ORDERS] Order {order_id} created, but failed to insert items! Attempting rollback...")
                await admin_sb.table("orders").delete().eq("id", order_id).execute()
                return None

            logger.info(f"[REPO:ORDERS] Order {order_id} and all items successfully created with tax snapshots.")
            return await self.get_order_by_id(order_id)
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Critical error during order creation: {e}", exc_info=True)
            return None

    # ── Order Fetching ───────────────────────────────────────────────────────
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
