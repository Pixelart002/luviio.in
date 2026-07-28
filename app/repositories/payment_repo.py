"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Path: app/repositories/payment_repo.py
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPaymentRepository:
    def __init__(self):
        pass
    
    async def has_active_pending_order(self, user_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("id").eq("customer_id", user_id).eq("status", "pending").limit(1).execute()
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error checking active pending order for user %s: %s", user_id, exc, exc_info=True)
            return False
        
    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        logger.info("[REPO:CART] Fetching cart for user: %s", user_id)
        try:
            res = await admin_sb.table("carts").select(
                "id, cart_items(id, product_id, quantity, price_snapshot, products(name, price, compare_price, stock, hsn_code, gst_percentage, is_active))"
            ).eq("user_id", user_id).maybe_single().execute()
            
            data = getattr(res, "data", None)
            return data.get("cart_items", []) if data else []
        except Exception as exc:
            logger.error("DB Error fetching cart items for user %s: %s", user_id, exc, exc_info=True)
            return []

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching address %s: %s", address_id, exc, exc_info=True)
            return None

    async def get_pricing_config(self) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            data = getattr(res, "data", None)
            return data or {"tax_rate": 18, "shipping_flat": 50, "shipping_threshold": 999, "currency": "INR"}
        except Exception as exc:
            logger.error("DB Error fetching pricing config: %s", exc, exc_info=True)
            return {"tax_rate": 18, "shipping_flat": 50, "shipping_threshold": 999, "currency": "INR"}

    async def get_customer_email(self, user_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            data = getattr(res, "data", None)
            return data["email"] if data and "email" in data else ""
        except Exception as exc:
            logger.error("DB Error fetching email for user %s: %s", user_id, exc, exc_info=True)
            return ""

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*").eq("customer_id", user_id).eq("idempotency_key", idempotency_key).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error checking idempotency key %s: %s", idempotency_key, exc, exc_info=True)
            return None

    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*, order_items(*, products(name, compare_price, hsn_code, gst_percentage))").eq("id", order_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching order %s: %s", order_id, exc, exc_info=True)
            return None

    async def create_pending_order_with_reservation(self, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "create_pending_order_with_reservation",
                {"p_order_data": order_data, "p_items": items}
            ).execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("RPC returned no data for pending order reservation.")
            return data
        except Exception as exc:
            logger.error("RPC Error reserving stock and creating order: %s", exc, exc_info=True)
            raise

    async def settle_order_transaction(self, order_id: str, pi_id: str, amount: float, user_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "settle_order_transaction",
                {"p_order_id": order_id, "p_pi_id": pi_id, "p_amount": amount, "p_user_id": user_id}
            ).execute()
            data = getattr(res, "data", None)
            return str(data) if data else "FAILED"
        except Exception as exc:
            logger.error("RPC Error settling order %s: %s", order_id, exc, exc_info=True)
            raise

    async def release_abandoned_order(self, order_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "cancel_order_and_release_stock",
                {"p_order_id": order_id}
            ).execute()
            data = getattr(res, "data", None)
            return str(data) if data else "FAILED"
        except Exception as exc:
            logger.error("RPC Error releasing stock for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def update_order_payment_intent(self, order_id: str, new_pi_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            # 🔥 FIX: Added missing closing bracket '}' for the update payload dictionary
            await admin_sb.table("orders").update({
                "stripe_payment_intent": new_pi_id
            }).eq("id", order_id).eq("status", "pending").execute()
        except Exception as exc:
            logger.error("DB Error updating payment intent for order %s: %s", order_id, exc, exc_info=True)
            raise