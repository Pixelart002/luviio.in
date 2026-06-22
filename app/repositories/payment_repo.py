"""
Payments Repository — ACID & JIT Hybrid Flow (Enterprise Grade)
===============================================================
Path: app/repositories/payment_repo.py

🔥 ARCHITECTURE UPGRADE: 
   Integrated Supabase PL/pgSQL RPCs for Atomic Row-Level Locking.
   Prevents Overselling, Race Conditions, and Double Settlements.
"""
import logging
from typing import Any, Dict, List, Optional
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPaymentRepository:
    def __init__(self):
        self.admin_sb = get_async_admin_supabase()

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict]:
        logger.info(f"[REPO:CART] Fetching cart for user: {user_id}")
        res = await self.admin_sb.table("carts").select(
            "id, cart_items(id, product_id, quantity, price_snapshot, products(name, price, stock, is_active))"
        ).eq("user_id", user_id).maybe_single().execute()
        
        data = getattr(res, "data", None)
        return data.get("cart_items", []) if data else []

    async def get_shipping_address(self, address_id: str, user_id: str) -> dict | None:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        res = await self.admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
        return getattr(res, "data", None)

    async def get_pricing_config(self) -> dict:
        res = await self.admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
        data = getattr(res, "data", None)
        return data or {"tax_rate": 18, "shipping_flat": 50, "shipping_threshold": 999, "currency": "INR"}

    async def get_customer_email(self, user_id: str) -> str:
        # Assuming table might be 'users' or 'profiles'. Kept as 'users' based on your snippet.
        res = await self.admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
        data = getattr(res, "data", None)
        return data["email"] if data else ""

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> dict | None:
        res = await self.admin_sb.table("orders").select("*").eq("customer_id", user_id).eq("idempotency_key", idempotency_key).maybe_single().execute()
        return getattr(res, "data", None)

    async def get_order_by_id(self, order_id: str) -> dict | None:
        res = await self.admin_sb.table("orders").select("*, order_items(*)").eq("id", order_id).maybe_single().execute()
        return getattr(res, "data", None)

    # ══════════════════════════════════════════════════════════════════════════════
    #  🔥 NEW: ACID COMPLIANT TRANSACTIONS (SUPERSEDES LEGACY METHODS)
    # ══════════════════════════════════════════════════════════════════════════════

    async def create_pending_order_with_reservation(self, order_data: dict, items: list) -> Dict[str, Any]:
        """Calls Postgres RPC to reserve stock and insert order atomically in 1 transaction."""
        res = await self.admin_sb.rpc(
            "create_pending_order_with_reservation",
            {"p_order_data": order_data, "p_items": items}
        ).execute()
        return getattr(res, "data", None)

    async def settle_order_transaction(self, order_id: str, pi_id: str, amount: float, user_id: str) -> str:
        """Executes row-locking update, creates ledger, and drops cart instantly."""
        res = await self.admin_sb.rpc(
            "settle_order_transaction",
            {"p_order_id": order_id, "p_pi_id": pi_id, "p_amount": amount, "p_user_id": user_id}
        ).execute()
        return getattr(res, "data", None)

    async def release_abandoned_order(self, order_id: str) -> str:
        """Restores stock and marks order as cancelled upon intent expiration."""
        res = await self.admin_sb.rpc(
            "cancel_order_and_release_stock",
            {"p_order_id": order_id}
        ).execute()
        return getattr(res, "data", None)

    # ══════════════════════════════════════════════════════════════════════════════
    #  ⚠️ LEGACY METHODS (Kept alive so other routers don't crash)
    # ══════════════════════════════════════════════════════════════════════════════

    async def clear_user_cart(self, user_id: str):
        cart_res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
        data = getattr(cart_res, "data", None)
        if data:
            await self.admin_sb.table("cart_items").delete().eq("cart_id", data["id"]).execute()
            logger.info(f"[REPO:CART] Cart {data['id']} cleared.")

    async def deduct_stock_for_order(self, order_id: str):
        # Now handled by create_pending_order_with_reservation internally
        pass

    async def update_order_status(self, order_id: str, status: str, payment_intent: str = None) -> dict | None:
        data = {"status": status}
        if payment_intent:
            data["stripe_payment_intent"] = payment_intent
        res = await self.admin_sb.table("orders").update(data).eq("id", order_id).execute()
        res_data = getattr(res, "data", None)
        return res_data[0] if res_data else None

    async def create_payment_record(self, order_id: str, pi_id: str, amount: float):
        # Now handled by settle_order_transaction internally
        pass