"""
Payment Repository — Async JIT Atomic Order Creation (HEAVILY LOGGED)
==================================================================
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
        logger.debug("[REPO:PRICING] Fetching pricing config from DB...")
        try:
            res = await self.admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            return res.data if res and res.data else {}
        except Exception as e:
            logger.error(f"[REPO:PRICING] Failed to fetch pricing config: {e}", exc_info=True)
            return {}

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        logger.info(f"[REPO:CART] Fetching cart for user: {user_id}")
        try:
            res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
            if not res or not res.data:
                logger.warning(f"[REPO:CART] No active cart found for user: {user_id}")
                return []
            
            cart_id = res.data["id"]
            items_res = await self.admin_sb.table("cart_items").select(
                "product_id, quantity, price_snapshot, products(name, price, stock, is_active)"
            ).eq("cart_id", cart_id).execute()
            
            items = items_res.data if items_res and items_res.data else []
            logger.info(f"[REPO:CART] Found {len(items)} items in cart {cart_id}")
            return items
        except Exception as e:
            logger.error(f"[REPO:CART] Error fetching cart items: {e}", exc_info=True)
            return []

    async def get_order_by_idempotency_key(self, user_id: str, key: str) -> Optional[Dict[str, Any]]:
        logger.debug(f"[REPO:ORDERS] Checking idempotency key: {key} for user: {user_id}")
        try:
            res = await self.admin_sb.table("orders").select("id, status, total_amount").eq("customer_id", user_id).eq("idempotency_key", key).limit(1).execute()
            if res and res.data:
                logger.info(f"[REPO:ORDERS] 🛑 Idempotency hit! Order already exists: {res.data[0]['id']}")
                return res.data[0]
            return None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Idempotency check failed: {e}", exc_info=True)
            return None

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        logger.debug(f"[REPO:ADDRESS] Fetching address {address_id} for user {user_id}")
        try:
            res = await self.admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
            return res.data if res and res.data else None
        except Exception as e:
            logger.error(f"[REPO:ADDRESS] Failed to fetch address: {e}", exc_info=True)
            return None

    async def lock_cart(self, user_id: str) -> None:
        """Lock the user's cart to prevent modifications during active checkout."""
        logger.info(f"[REPO:CART] Locking cart for user: {user_id}")
        try:
            await self.admin_sb.table("carts").update({"locked": True}).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"[REPO:CART] Failed to lock cart for user {user_id}: {e}", exc_info=True)

    async def unlock_cart(self, user_id: str) -> None:
        """Unlock the user's cart, allowing modifications again."""
        logger.info(f"[REPO:CART] Unlocking cart for user: {user_id}")
        try:
            await self.admin_sb.table("carts").update({"locked": False}).eq("user_id", user_id).execute()
        except Exception as e:
            logger.error(f"[REPO:CART] Failed to unlock cart for user {user_id}: {e}", exc_info=True)

    async def clear_user_cart(self, user_id: str) -> None:
        logger.info(f"[REPO:CART] Attempting to clear cart for user {user_id}")
        try:
            res = await self.admin_sb.table("carts").select("id").eq("user_id", user_id).maybe_single().execute()
            if res and res.data:
                cart_id = res.data["id"]
                del_res = await self.admin_sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
                logger.info(f"[REPO:CART] ✅ Cart cleared successfully! Items deleted: {len(del_res.data) if del_res.data else 0}")
        except Exception as e:
            logger.error(f"[REPO:CART] ❌ Failed to clear cart: {e}", exc_info=True)

    async def create_order_from_payment_jit(self, order_data: dict, items_to_deduct: list) -> Dict[str, Any]:
        logger.info(f"[REPO:JIT] Starting Atomic JIT Order Creation for User: {order_data.get('customer_id')}")
        deducted_items = []
        try:
            # 1. Deduct Stock
            for item in items_to_deduct:
                pid = item["product_id"]
                qty = item["quantity"]
                name = item.pop("product_name", "Unknown") 
                
                logger.debug(f"[REPO:JIT] Decrementing stock for {name} ({pid}) by {qty}")
                decrement_res = await self.admin_sb.rpc("decrement_stock", {"p_id": pid, "p_qty": qty}).execute()
                if not decrement_res or not decrement_res.data:
                    raise RuntimeError(f"Insufficient stock for {name}")
                deducted_items.append((pid, qty))

            # 2. Create Order
            logger.debug(f"[REPO:JIT] Inserting into orders table. Payload keys: {list(order_data.keys())}")
            order_res = await self.admin_sb.table("orders").insert(order_data).execute()
            if not order_res or not order_res.data: 
                raise RuntimeError("Order creation returned empty data from DB.")
            order = order_res.data[0]
            logger.info(f"[REPO:JIT] ✅ Order created successfully: {order['id']}")
            
            # 3. Create Order Items
            for item in items_to_deduct: 
                item["order_id"] = order["id"]
            
            logger.debug(f"[REPO:JIT] Inserting {len(items_to_deduct)} items into order_items table.")
            await self.admin_sb.table("order_items").insert(items_to_deduct).execute()
            
            return order

        except Exception as e:
            logger.critical(f"[REPO:JIT] 🚨 JIT Transaction failed: {e}. Executing Rollback!", exc_info=True)
            # Rollback Stock
            for pid, qty in deducted_items:
                logger.info(f"[REPO:ROLLBACK] Incrementing stock back for {pid} by {qty}")
                await self.admin_sb.rpc("increment_stock", {"p_id": pid, "p_qty": qty}).execute()
            raise RuntimeError(f"Order processing failed: {e}")

    # 🔥🔥 THE CULPRIT METHOD (Heavily Logged Now) 🔥🔥
    async def create_payment_record(self, order_id: str, pi_id: str, amount: float, currency: str = "INR") -> None:
        logger.info(f"[REPO:PAYMENTS] ⏳ Attempting to insert into 'payments' table | Order: {order_id} | Intent: {pi_id} | Amount: {amount}")
        try:
            payload = {
                "order_id": order_id, 
                "stripe_payment_intent_id": pi_id,
                "amount": amount, 
                "currency": currency, 
                "status": "completed", 
                "payment_method": "stripe"
            }
            logger.debug(f"[REPO:PAYMENTS] Payload: {payload}")
            
            res = await self.admin_sb.table("payments").insert(payload).execute()
            
            if res and getattr(res, "data", None):
                logger.info(f"[REPO:PAYMENTS] ✅ Payment record saved successfully! Payment Row ID: {res.data[0].get('id')}")
            else:
                logger.error(f"[REPO:PAYMENTS] ❌ Insert executed but no data returned. Full Response: {res}")
                
        except Exception as e:
            # Ab error chhupega nahi! Pura stack trace console mein dikhega.
            logger.error(f"[REPO:PAYMENTS] 🚨 FATAL DB ERROR inserting payment record: {e}", exc_info=True)
            # Optional: Uncomment below line to crash the process if payment log fails
            # raise RuntimeError(f"Failed to save payment to DB: {e}")

    async def get_customer_email(self, customer_id: str) -> str:
        if not customer_id: return ""
        try:
            res = await self.admin_sb.table("users").select("email").eq("id", customer_id).limit(1).execute()
            return res.data[0].get("email", "") if res and res.data else ""
        except Exception:
            return ""

    async def get_order_by_pi(self, pi_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = await self.admin_sb.table("orders").select("id, status, total_amount, customer_id, order_items(*)").eq("stripe_payment_intent", pi_id).maybe_single().execute()
            return res.data if res and res.data else None
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Failed to fetch order by PI {pi_id}: {e}", exc_info=True)
            return None

    async def update_order_status(self, order_id: str, new_status: str, expected_status: str) -> bool:
        logger.info(f"[REPO:ORDERS] Updating order {order_id} status from {expected_status} -> {new_status}")
        try:
            res = await self.admin_sb.table("orders").update({"status": new_status}).eq("id", order_id).eq("status", expected_status).execute()
            success = bool(res and res.data)
            if not success:
                logger.warning(f"[REPO:ORDERS] Status update failed. Order {order_id} might not be in '{expected_status}' state.")
            return success
        except Exception as e:
            logger.error(f"[REPO:ORDERS] Error updating order status: {e}", exc_info=True)
            return False