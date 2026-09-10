"""
Order Repository — Async Enterprise Grade.

Customer order history uses a lightweight summary projection; full order items
remain available through get_order_by_id for the order-detail view.
"""
import logging
from typing import Any, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

ORDER_ITEMS_SELECT = "*, order_items(*, products(name, image_url, slug, price, hsn_code, gst_percentage, compare_price))"
USER_ORDER_SELECT = "id, order_number, status, total_amount, created_at"


class AsyncOrderRepository:
    def __init__(self):
        pass

    async def get_order_by_id(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        """Resolve either an internal UUID (server-side) or the existing order_number."""
        admin_sb = await get_async_admin_supabase()
        try:
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT)
            try:
                UUID(str(order_id))
                q = q.eq("id", str(order_id))
            except (ValueError, TypeError):
                q = q.eq("order_number", str(order_id))
            if user_id:
                q = q.eq("customer_id", user_id)
            res = await q.maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed to resolve order reference: {e}", exc_info=True)
            return None

    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        logger.info(f"[REPO:ORDERS] Cancelling order {order_id} and restoring stock.")
        try:
            q = admin_sb.table("orders").select("id").eq("id", order_id).in_("status", ["pending", "paid", "processing"])
            if user_id:
                q = q.eq("customer_id", user_id)
            check = await q.execute()
            if not check or not check.data:
                logger.warning(f"[REPO:ORDERS] Cancel failed. Order {order_id} invalid state or access denied.")
                return None
            result = await admin_sb.rpc("cancel_order_and_release_stock", {"p_order_id": order_id, "p_reason": "customer_requested" if user_id else "admin_requested"}).execute()
            outcome = getattr(result, "data", None)
            if outcome == "ORDER_ALREADY_FULFILLED":
                logger.info(f"[REPO:ORDERS] Cancel refused for {order_id} — already shipped/delivered.")
                return None
            if outcome not in ("CANCELLED", "ALREADY_CANCELLED"):
                logger.warning(f"[REPO:ORDERS] Unexpected outcome cancelling order {order_id}: {outcome}")
                return None
            return await self.get_order_by_id(order_id)
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error during cancel & restore for {order_id}: {e}", exc_info=True)
            return None

    async def update_order_status_safe(self, order_id: str, updates: dict, expected_status: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            check = await admin_sb.table("orders").select("id").eq("id", order_id).eq("status", expected_status).execute()
            if not check or not check.data:
                return None
            res = await admin_sb.rpc("rpc_admin_update_order_status", {"p_order_id": order_id, "p_new_status": updates.get("status"), "p_tracking_number": updates.get("tracking_number"), "p_notes": updates.get("notes")}).execute()
            return res.data if res and res.data else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error updating order {order_id}: {e}", exc_info=True)
            return None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(USER_ORDER_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
            if status_filter:
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching user orders: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to load order history right now.") from e

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[dict], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
            if status_filter:
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed fetching all orders: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to load orders right now.") from e

    async def get_order_for_admin_update(self, order_id: str) -> Optional[dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
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
        except Exception:
            return None
