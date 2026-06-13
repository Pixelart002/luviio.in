"""
Payments Repository — AOT (Pending Order) Flow
================================================
Path: app/repositories/payment_repo.py
"""
import logging
from typing import Any, Dict, List
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
        
        items = res.data.get("cart_items", []) if res.data else []
        logger.info(f"[REPO:CART] Found {len(items)} items in cart {res.data.get('id') if res.data else 'N/A'}")
        return items

    async def clear_user_cart(self, user_id: str):
        cart_res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
        if cart_res.data:
            await self.admin_sb.table("cart_items").delete().eq("cart_id", cart_res.data["id"]).execute()
            logger.info(f"[REPO:CART] Cart {cart_res.data['id']} cleared.")

    async def get_shipping_address(self, address_id: str, user_id: str) -> dict | None:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        res = await self.admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
        return res.data

    async def get_pricing_config(self) -> dict:
        res = await self.admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
        return res.data or {"tax_rate": 18, "shipping_flat": 50, "shipping_threshold": 999, "currency": "INR"}

    async def get_customer_email(self, user_id: str) -> str:
        res = await self.admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
        return res.data["email"] if res.data else ""

    # ── 1. NAYA FLOW: Create Order as 'Pending' Before Payment ──
    async def create_pending_order(self, order_data: dict, items: list) -> dict:
        logger.info(f"[REPO:ORDERS] Creating pending order for user: {order_data.get('customer_id')}")
        # Step 1: Insert Order (Status is already 'pending' by default in DB)
        order_res = await self.admin_sb.table("orders").insert(order_data).execute()
        order = order_res.data[0]
        
        # Step 2: Insert Order Items
        for item in items:
            item["order_id"] = order["id"]
        await self.admin_sb.table("order_items").insert(items).execute()
        
        # Step 3: Reserve Stock (Minus from DB)
        for item in items:
            prod_res = await self.admin_sb.table("products").select("stock").eq("id", item["product_id"]).maybe_single().execute()
            if prod_res.data:
                new_stock = max(0, prod_res.data["stock"] - item["quantity"])
                await self.admin_sb.table("products").update({"stock": new_stock}).eq("id", item["product_id"]).execute()
        
        return order

    # ── 2. NAYA FLOW: Update Status when Webhook/Confirm Hits ──
    async def update_order_status(self, order_id: str, status: str, payment_intent: str = None) -> dict:
        data = {"status": status}
        if payment_intent:
            data["stripe_payment_intent"] = payment_intent
        res = await self.admin_sb.table("orders").update(data).eq("id", order_id).execute()
        return res.data[0] if res.data else None

    # ── 3. NAYA FLOW: Restore Stock if Payment Fails ──
    async def restore_stock_for_order(self, order_id: str):
        items_res = await self.admin_sb.table("order_items").select("*").eq("order_id", order_id).execute()
        for item in items_res.data or []:
            prod_res = await self.admin_sb.table("products").select("stock").eq("id", item["product_id"]).maybe_single().execute()
            if prod_res.data:
                new_stock = prod_res.data["stock"] + item["quantity"]
                await self.admin_sb.table("products").update({"stock": new_stock}).eq("id", item["product_id"]).execute()

    # ── Helpers ──
    async def create_payment_record(self, order_id: str, pi_id: str, amount: float):
        await self.admin_sb.table("payments").insert({
            "order_id": order_id,
            "stripe_payment_intent_id": pi_id,
            "amount": amount,
            "currency": "INR",
            "status": "succeeded",
            "payment_method": "card"
        }).execute()

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> dict | None:
        res = await self.admin_sb.table("orders").select("*").eq("customer_id", user_id).eq("idempotency_key", idempotency_key).maybe_single().execute()
        return res.data

    async def get_order_by_id(self, order_id: str) -> dict | None:
        res = await self.admin_sb.table("orders").select("*, order_items(*)").eq("id", order_id).maybe_single().execute()
        return res.data