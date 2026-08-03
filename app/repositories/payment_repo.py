"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Path: app/repositories/payment_repo.py

Lifecycle-hardening changes in this version:
  * record_payment_attempt() -- THE single write path for both `payments`
    (one row per order -- the rollup header) and `payment_attempts` (one
    row per PaymentIntent -- the detail log). Called for intent creation,
    every retry, and failure recording. Success goes through
    settle_order_transaction() instead (needs its own order-status guard).
  * get_attempt_count() -- reads `total_attempts` directly off the order's
    single payments header row.
  * record_webhook_event() / mark_webhook_event_processed() -- idempotency
    ledger so a retried Stripe webhook delivery is never processed twice,
    while a delivery that crashed mid-processing (never reached
    mark_webhook_event_processed) is correctly allowed to be retried.
  * update_order_payment_intent() -- now returns whether the link actually
    happened (order might have flipped to a terminal state concurrently),
    instead of silently no-op'ing.
  * release_abandoned_order() -- accepts a `reason` for the cancellation note.
  * list_stale_pending_orders() -- powers the abandoned-checkout cron sweep.
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
        """
        Returns one of: 'SETTLED' | 'ALREADY_PAID' | 'ORDER_ALREADY_CANCELLED'.
        Callers MUST handle 'ORDER_ALREADY_CANCELLED' -- it means the customer's
        payment succeeded on Stripe's side after the order was already
        cancelled + stock released on ours. The RPC itself never resurrects
        the order; the caller is responsible for triggering a refund.
        """
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

    async def release_abandoned_order(self, order_id: str, reason: str = "order_cancelled") -> str:
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc(
                "cancel_order_and_release_stock",
                {"p_order_id": order_id, "p_reason": reason}
            ).execute()
            data = getattr(res, "data", None)
            return str(data) if data else "FAILED"
        except Exception as exc:
            logger.error("RPC Error releasing stock for order %s: %s", order_id, exc, exc_info=True)
            raise

    async def update_order_payment_intent(self, order_id: str, new_pi_id: str) -> bool:
        """
        Returns True if the new intent was actually linked, False if the
        order was no longer 'pending' (e.g. cancelled by the abandoned-
        checkout sweep or another webhook in a race). Callers MUST check
        this -- previously this failure mode was silent, meaning a
        client_secret could be handed back for an intent that was never
        actually attached to a live order.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").update({
                "stripe_payment_intent": new_pi_id
            }).eq("id", order_id).eq("status", "pending").execute()
            linked = bool(getattr(res, "data", None))
            if not linked:
                logger.warning(
                    "[PAYMENT] Refused to link new intent %s -- Order %s is no longer 'pending'.",
                    new_pi_id, order_id
                )
            return linked
        except Exception as exc:
            logger.error("DB Error updating payment intent for order %s: %s", order_id, exc, exc_info=True)
            raise

    # ─────────────────────────────────────────────────────────────────────
    # 🔥 NEW: payments table -- never-missing, self-healing writes
    # ─────────────────────────────────────────────────────────────────────

    async def record_payment_attempt(
        self,
        order_id: str,
        user_id: Optional[str],
        pi_id: str,
        amount: float,
        status: str,
        payment_method: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        The ONE place that writes to `payments` (one row per order -- the
        rollup header: total_attempts, latest_attempt_number,
        successful_attempt_number, etc.) and `payment_attempts` (one row
        per PaymentIntent -- the detail log), atomically, inside the
        `record_payment_attempt` RPC. No triggers are involved -- this is
        the single, explicit, readable code path for every write to either
        table.

        Called for:
          * a fresh PaymentIntent at checkout      -> status='requires_payment_method'
          * every retry's fresh PaymentIntent       -> status='requires_payment_method'
          * a webhook/client-reported failure       -> status='failed' (+ error_code/error_message)
        Success is handled by settle_order_transaction() instead, since
        that also needs to flip the order to 'paid' with its own guard
        against resurrecting a cancelled order.

        Non-fatal by design: logs and continues on error so a payments/
        payment_attempts write issue never blocks checkout, retry, or
        webhook processing.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("record_payment_attempt", {
                "p_order_id": order_id,
                "p_user_id": user_id,
                "p_pi_id": pi_id,
                "p_amount": amount,
                "p_status": status,
                "p_payment_method": payment_method,
                "p_error_code": error_code,
                "p_error_message": error_message,
                "p_ip_address": ip_address,
                "p_user_agent": user_agent,
            }).execute()
        except Exception as exc:
            logger.error("RPC Error recording payment attempt for PI %s: %s", pi_id, exc, exc_info=True)

    async def get_attempt_count(self, order_id: str) -> int:
        """
        Reads `total_attempts` directly off the order's single payments
        header row. Used to cap retries the way Amazon does: after too
        many failed attempts on one order, further retries are blocked
        until the abandoned-checkout sweep eventually cancels it.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("payments").select("total_attempts").eq("order_id", order_id).maybe_single().execute()
            data = getattr(res, "data", None)
            return (data or {}).get("total_attempts") or 0
        except Exception as exc:
            logger.error("DB Error reading attempt count for order %s: %s", order_id, exc, exc_info=True)
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # 🔥 NEW: webhook helpers
    # ─────────────────────────────────────────────────────────────────────

    async def get_order_by_payment_intent(self, pi_id: str) -> Optional[Dict[str, Any]]:
        """Used by webhook to find an order via its Stripe Payment Intent ID."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select("*").eq("stripe_payment_intent", pi_id).maybe_single().execute()
            return getattr(res, "data", None)
        except Exception as exc:
            logger.error("DB Error fetching order by PI %s: %s", pi_id, exc, exc_info=True)
            return None

    async def record_webhook_event(self, event_id: str, event_type: str, pi_id: Optional[str]) -> bool:
        """
        🔥 FIX: previously this marked an event as "seen" the instant it
        arrived -- so if processing then crashed for ANY reason (a bug, a
        transient DB error) and we returned 500, Stripe's retry would be
        told "already handled, skip" and get a 200 back. Stripe stops
        retrying after that. Net effect: a real successful payment could
        get silently stuck in 'pending' forever, with no further signal
        from Stripe. Confirmed in production logs after the ip_address
        type bug caused settle_order_transaction to throw.

        Now uses claim_webhook_event(), which only returns False (skip)
        if this event was already marked FULLY PROCESSED by a prior,
        successful run. A delivery for an event that was received but
        never finished (crashed) is correctly treated as "not done yet"
        and reprocessed -- safe, because every RPC in this flow already
        guards its own idempotency (ALREADY_PAID / ALREADY_CANCELLED).

        Caller MUST call mark_processed() after successfully handling the
        event -- see handle_webhook().

        Fails OPEN on unexpected DB errors: a hiccup in the ledger table
        should never cause us to silently drop a legitimate webhook.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.rpc("claim_webhook_event", {
                "p_event_id": event_id,
                "p_event_type": event_type,
                "p_pi_id": pi_id,
            }).execute()
            should_process = getattr(res, "data", None)
            return True if should_process is None else bool(should_process)
        except Exception as exc:
            logger.error("DB Error claiming webhook event %s: %s", event_id, exc, exc_info=True)
            return True

    async def mark_webhook_event_processed(self, event_id: str) -> None:
        """Call ONLY after the event's handler has completed without raising."""
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("mark_webhook_event_processed", {"p_event_id": event_id}).execute()
        except Exception as exc:
            logger.error("DB Error marking webhook event %s processed: %s", event_id, exc, exc_info=True)

    async def update_order_status_via_rpc(self, order_id: str, new_status: str, notes: str) -> None:
        """Used by webhook to push FSM updates like Refunds or Dispute Alerts."""
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("rpc_admin_update_order_status", {
                "p_order_id": order_id,
                "p_new_status": new_status,
                "p_notes": notes
            }).execute()
        except Exception as exc:
            logger.error("Webhook RPC Error updating status for %s: %s", order_id, exc, exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # 🔥 NEW: abandoned-checkout cron support
    # ─────────────────────────────────────────────────────────────────────

    async def list_stale_pending_orders(self, cutoff_iso: str) -> List[Dict[str, Any]]:
        """Orders stuck in 'pending' created before `cutoff_iso` -- candidates for the abandoned-checkout sweep."""
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("orders").select(
                "id, customer_id, stripe_payment_intent, created_at"
            ).eq("status", "pending").lt("created_at", cutoff_iso).execute()
            return getattr(res, "data", None) or []
        except Exception as exc:
            logger.error("DB Error listing stale pending orders: %s", exc, exc_info=True)
            return []