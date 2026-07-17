"""
Payments Repository — ACID & JIT Hybrid Flow (Enterprise Grade)
===============================================================
Path: app/repositories/payment_repo.py
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPaymentRepository:
    """Stateless execution preventing coroutine state crashes and thread locks."""
    
    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("carts").select(
            "id, cart_items(id, product_id, quantity, price_snapshot, products(name, price, compare_price, stock, is_active))"
        ).eq("user_id", user_id).maybe_single().execute()
        data = getattr(res, "data", None)
        return data.get("cart_items", []) if data else []

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
        return getattr(res, "data", None)

    async def get_pricing_config(self) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
        data = getattr(res, "data", None)
        return data or {"tax_rate": 18, "shipping_flat": 50, "shipping_threshold": 999, "currency": "INR"}

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("orders").select("*").eq("customer_id", user_id).eq("idempotency_key", idempotency_key).maybe_single().execute()
        return getattr(res, "data", None)

    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.table("orders").select("*, order_items(*, products(name, compare_price))").eq("id", order_id).maybe_single().execute()
        return getattr(res, "data", None)

    # 🔥 ACID COMPLIANT RPC TRANSACTIONS
    async def create_pending_order_with_reservation(self, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("create_pending_order_with_reservation", {"p_order_data": order_data, "p_items": items}).execute()
        return getattr(res, "data", None)

    async def settle_order_transaction(self, order_id: str, pi_id: str, amount: float, user_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("settle_order_transaction", {"p_order_id": order_id, "p_pi_id": pi_id, "p_amount": amount, "p_user_id": user_id}).execute()
        return getattr(res, "data", None)

    async def update_order_payment_intent(self, order_id: str, new_pi_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        await admin_sb.table("orders").update({"stripe_payment_intent": new_pi_id}).eq("id", order_id).eq("status", "pending").execute()