"""
Payment Repository — Async JIT Atomic Order Creation
====================================================
Path: app/repositories/payment_repo.py
"""
import logging
from typing import Any, Dict, Optional, List
from app.core.supabase import get_async_admin_supabase

logger = logging.getLogger(__name__)

class AsyncPaymentRepository:
    def __init__(self):
        self.admin_sb = get_async_admin_supabase()
    
    async def get_pricing_config(self) -> dict[str, Any]:
        try:
            res = await self.admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            return res.data if res and res.data else {}
        except Exception:
            return {}

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
        if not res or not res.data:
            return []
        
        cart_id = res.data["id"]
        items_res = await self.admin_sb.table("cart_items").select(
            "product_id, quantity, price_snapshot, products(name, price, stock, is_active)"
        ).eq("cart_id", cart_id).execute()
        return items_res.data or []

    async def get_order_by_idempotency_key(self, user_id: str, key: str) -> Optional[Dict[str, Any]]:
        res = await self.admin_sb.table("orders").select("id, status, total_amount").eq("customer_id", user_id).eq("idempotency_key", key).maybe_single().execute()
        return res.data

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        res = await self.admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
        return res.data

    async def clear_user_cart(self, user_id: str) -> None:
        res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
        if res and res.data:
            await self.admin_sb.table("cart_items").delete().eq("cart_id", res.data["id"]).execute()

    async def create_order_from_payment_jit(self, order_data: dict, items_to_deduct: list) -> Dict[str, Any]:
        deducted_items = []
        try:
            # 1. Batch Stock Deduction (Awaited sequentially to ensure integrity)
            for item in items_to_deduct:
                pid = item["product_id"]
                qty = item["quantity"]
                name = item.pop("product_name", "Unknown") 
                
                decrement_res = await self.admin_sb.rpc("decrement_product_stock", {"p_id": pid, "p_qty": qty}).execute()
                if not decrement_res or not decrement_res.data:
                    raise RuntimeError(f"Insufficient stock for {name}")
                deducted_items.append((pid, qty))

            # 2. Insert Order (PAID)
            order_res = await self.admin_sb.table("orders").insert(order_data).execute()
            order = order_res.data[0]
            
            # 3. Insert Items
            for item in items_to_deduct: item["order_id"] = order["id"]
            await self.admin_sb.table("order_items").insert(items_to_deduct).execute()
            return order

        except Exception as e:
            logger.critical(f"[ROLLBACK] JIT Transaction failed, restoring stock: {e}")
            for pid, qty in deducted_items:
                await self.admin_sb.rpc("increment_product_stock", {"p_id": pid, "p_qty": qty}).execute()
            raise RuntimeError(f"Order processing failed: {e}")

    async def create_payment_record(self, order_id: str, pi_id: str, amount: float, currency: str = "INR") -> None:
        try:
            await self.admin_sb.table("payments").insert({
                "order_id": order_id, "stripe_payment_intent_id": pi_id,
                "amount": amount, "currency": currency, "status": "completed", "payment_method": "stripe"
            }).execute()
        except Exception as e:
            logger.warning("Failed to insert payment record: %s", e)

    async def get_customer_email(self, customer_id: str) -> str:
        if not customer_id: return ""
        try:
            res = await self.admin_sb.table("users").select("email").eq("id", customer_id).limit(1).execute()
            return res.data[0].get("email", "") if res and res.data else ""
        except Exception:
            return ""

    async def get_order_by_pi(self, pi_id: str) -> Optional[Dict[str, Any]]:
        res = await self.admin_sb.table("orders").select("id, status, total_amount, customer_id, order_items(*)").eq("stripe_payment_intent", pi_id).maybe_single().execute()
        return res.data

    async def update_order_status(self, order_id: str, new_status: str, expected_status: str) -> bool:
        res = await self.admin_sb.table("orders").update({"status": new_status}).eq("id", order_id).eq("status", expected_status).execute()
        return bool(res and res.data)