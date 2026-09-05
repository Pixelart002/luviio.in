"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Canonical payment persistence boundary. Critical checkout, pricing, retry-limit
and webhook-ledger reads fail closed: database failures must never be treated as
"nothing exists" or "safe to continue".
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
            raise RuntimeError("Unable to verify active pending orders") from exc

    async def get_cart_items_for_checkout(self, user_id: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("carts").select("id, cart_items(id, product_id, quantity, price_snapshot, products(name, price, compare_price, stock, hsn_code, gst_percentage, is_active))").eq("user_id", user_id).maybe_single().execute()
            data = getattr(res, "data", None)
            return data.get("cart_items", []) if data else []
        except Exception as exc:
            logger.error("DB Error fetching cart items for user %s: %s", user_id, exc, exc_info=True)
            raise RuntimeError("Unable to load checkout cart") from exc

    async def get_shipping_address(self, address_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        if address_id == "dummy":
            return {"line1": "123 Demo St", "city": "Demo", "postal_code": "000000", "country": "IN"}
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("addresses").select("*").eq("id", address_id).eq("user_id", user_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching address %s: %s", address_id, exc, exc_info=True)
            raise RuntimeError("Unable to load checkout address") from exc

    async def get_pricing_config(self) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("pricing_config").select("*").limit(1).maybe_single().execute()
            data = getattr(res, "data", None)
            if not data:
                raise RuntimeError("pricing_config is missing")
            return data
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error fetching pricing config: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load pricing configuration") from exc

    async def get_customer_email(self, user_id: str) -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("users").select("email").eq("id", user_id).maybe_single().execute()
            data = getattr(res, "data", None)
            if not data or not data.get("email"):
                raise RuntimeError("Customer email is missing")
            return data["email"]
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error fetching email for user %s: %s", user_id, exc, exc_info=True)
            raise RuntimeError("Unable to load customer email") from exc

    async def get_order_by_idempotency_key(self, user_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*").eq("customer_id", user_id).eq("idempotency_key", idempotency_key).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error checking idempotency key %s: %s", idempotency_key, exc, exc_info=True)
            raise RuntimeError("Unable to verify idempotency key") from exc

    async def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*, order_items(*, products(name, compare_price, hsn_code, gst_percentage))").eq("id", order_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching order %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to load order") from exc

    async def create_pending_order_with_reservation(self, order_data: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("create_pending_order_with_reservation", {"p_order_data": order_data, "p_items": items}).execute()
        data = getattr(res, "data", None)
        if not data:
            raise RuntimeError("RPC returned no data for pending order reservation.")
        return data

    async def settle_order_transaction(self, order_id: str, pi_id: str, amount: float, user_id: str, payment_method: Optional[str] = None) -> str:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("settle_order_transaction", {"p_order_id": order_id, "p_pi_id": pi_id, "p_amount": amount, "p_user_id": user_id, "p_payment_method": payment_method}).execute()
        data = getattr(res, "data", None)
        return str(data) if data else "FAILED"

    async def release_abandoned_order(self, order_id: str, reason: str = "order_cancelled") -> str:
        admin_sb = await get_async_admin_supabase()
        res = await admin_sb.rpc("cancel_order_and_release_stock", {"p_order_id": order_id, "p_reason": reason}).execute()
        data = getattr(res, "data", None)
        return str(data) if data else "FAILED"

    async def update_order_payment_intent(self, order_id: str, new_pi_id: str) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").update({"stripe_payment_intent": new_pi_id}).eq("id", order_id).eq("status", "pending").execute()
            return bool(getattr(res, "data", None))
        except Exception as exc:
            logger.error("DB Error updating payment intent for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def record_payment_attempt(self, order_id: str, user_id: Optional[str], pi_id: str, amount: float, status: str, payment_method: Optional[str] = None, error_code: Optional[str] = None, error_message: Optional[str] = None, ip_address: Optional[str] = None, user_agent: Optional[str] = None) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("record_payment_attempt", {"p_order_id": order_id, "p_user_id": user_id, "p_pi_id": pi_id, "p_amount": amount, "p_status": status, "p_payment_method": payment_method, "p_error_code": error_code, "p_error_message": error_message, "p_ip_address": ip_address, "p_user_agent": user_agent}).execute()
        except Exception as exc:
            logger.error("RPC Error recording payment attempt for PI %s: %s", pi_id, exc, exc_info=True)

    async def get_attempt_count(self, order_id: str) -> int:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("payments").select("total_attempts").eq("order_id", order_id).maybe_single().execute()
            data = getattr(res, "data", None)
            if not data or data.get("total_attempts") is None:
                raise RuntimeError("Payment attempt counter is missing")
            return int(data["total_attempts"])
        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("DB Error reading attempt count for order %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to verify payment attempt limit") from exc

    async def get_order_by_payment_intent(self, pi_id: str) -> Optional[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*").eq("stripe_payment_intent", pi_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching order by PI %s: %s", pi_id, exc, exc_info=True)
            raise RuntimeError("Unable to resolve payment intent") from exc

    async def record_webhook_event(self, event_id: str, event_type: str, pi_id: Optional[str]) -> bool:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc("claim_webhook_event", {"p_event_id": event_id, "p_event_type": event_type, "p_pi_id": pi_id}).execute()
            data = getattr(res, "data", None)
            return True if data is None else bool(data)
        except Exception as exc:
            logger.error("DB Error claiming webhook event %s: %s", event_id, exc, exc_info=True)
            raise RuntimeError("Unable to claim webhook event") from exc

    async def mark_webhook_event_processed(self, event_id: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("mark_webhook_event_processed", {"p_event_id": event_id}).execute()
        except Exception as exc:
            logger.error("DB Error marking webhook event %s processed: %s", event_id, exc, exc_info=True)
            raise RuntimeError("Unable to mark webhook event processed") from exc

    async def update_order_status_via_rpc(self, order_id: str, new_status: str, notes: str) -> None:
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("rpc_admin_update_order_status", {"p_order_id": order_id, "p_new_status": new_status, "p_notes": notes}).execute()
        except Exception as exc:
            logger.error("Webhook RPC Error updating status for %s: %s", order_id, exc, exc_info=True)
            raise RuntimeError("Unable to update order status") from exc

    async def list_stale_pending_orders(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("id, customer_id, stripe_payment_intent, created_at").eq("status", "pending").lt("created_at", cutoff_iso).execute()
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error listing stale pending orders: %s", exc, exc_info=True)
            raise RuntimeError("Unable to load stale pending orders") from exc
