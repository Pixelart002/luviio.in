"""
Order Repository — Hardened Async Stateless Grade
=================================================
Path: app/repositories/order_repo.py
"""
import logging
from typing import Any, Optional, Tuple, List, Dict
from app.core.supabase import get_async_admin_supabase
from app.enums.order_status import OrderStatus

logger = logging.getLogger(__name__)

# Centralized Query Constants (SSOT)
ORDER_ITEMS_SELECT = "*, order_items(*, products(image_url, slug))"

class AsyncOrderRepository:
    """Stateless execution preventing coroutine state crashes and thread locks."""
    
    async def get_order_by_id(self, order_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT).eq("id", order_id)
            if user_id: 
                q = q.eq("customer_id", user_id)
            res = await q.maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error("Failed to fetch order %s: %s", order_id, e)
            return None

    async def cancel_order_and_restore_stock(self, order_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Atomically cancels pending/paid orders and increments stock via database RPC."""
        admin_sb = await get_async_admin_supabase()
        try:
            q = admin_sb.table("orders").update({"status": OrderStatus.CANCELLED.value}) \
                .eq("id", order_id) \
                .in_("status", [OrderStatus.PENDING.value, OrderStatus.PAID.value])
            
            if user_id: 
                q = q.eq("customer_id", user_id)
            
            res = await q.execute()
            if not res or not res.data:
                logger.warning("Order cancellation failed in DB for order %s", order_id)
                return None
                
            updated_order = res.data[0]
            logger.info("Order %s marked as cancelled. Triggering stock restoration...", order_id)

            # Best-effort asynchronous inventory restoration
            items_res = await admin_sb.table("order_items").select("product_id, quantity").eq("order_id", order_id).execute()
            for item in (items_res.data or []):
                if item.get("product_id"):
                    try:
                        await admin_sb.rpc("increment_stock", {
                            "p_id": item["product_id"],
                            "p_qty": item["quantity"]
                        }).execute()
                    except Exception as exc:
                        logger.error("Stock restore RPC failed for product %s: %s", item["product_id"], exc)
            
            return updated_order
        except Exception as e:
            logger.error("Critical error during order cancel & restore for %s: %s", order_id, e)
            return None

    async def update_order_status_safe(self, order_id: str, updates: Dict[str, Any], expected_status: str) -> Optional[Dict[str, Any]]:
        """Optimistic concurrency lock ensuring state hasn't shifted before updating."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").update(updates).eq("id", order_id).eq("status", expected_status).execute()
            return res.data[0] if res and res.data else None
        except Exception as e:
            logger.error("Error executing safe order update for %s: %s", order_id, e)
            return None

    async def get_user_orders(self, user_id: str, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(ORDER_ITEMS_SELECT, count="exact").eq("customer_id", user_id).order("created_at", desc=True)
            if status_filter: 
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error("Failed fetching user orders for %s: %s", user_id[:8], e)
            return [], 0

    async def get_all_orders(self, status_filter: Optional[str], page: int, page_size: int) -> Tuple[List[Dict[str, Any]], int]:
        admin_sb = await get_async_admin_supabase()
        offset = (page - 1) * page_size
        try:
            q = admin_sb.table("orders").select(f"{ORDER_ITEMS_SELECT}, users(email, full_name)", count="exact").order("created_at", desc=True)
            if status_filter: 
                q = q.eq("status", status_filter)
            res = await q.range(offset, offset + page_size - 1).execute()
            return res.data or [], res.count or 0
        except Exception as e:
            logger.error("Failed fetching global orders: %s", e)
            return [], 0

    async def get_order_for_admin_update(self, order_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("status, stripe_payment_intent, customer_id").eq("id", order_id).maybe_single().execute()
            return res.data if res else None
        except Exception as e:
            logger.error("Error fetching order for admin update %s: %s", order_id, e)
            return None

    async def get_user_email(self, user_id: str) -> Optional[str]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            return res.data["email"] if res and res.data else None
        except Exception as e:
            logger.warning("Could not resolve email for user %s: %s", user_id[:8], e)
            return None