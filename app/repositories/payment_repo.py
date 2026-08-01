"""
Payments Repository -- ACID & JIT Hybrid Flow (Enterprise Grade & GST Ready)
============================================================================
Path: app/repositories/payment_repo.py

Lifecycle-hardening changes in this version:
  * create_or_touch_payment_intent_record() -- eagerly writes a `payments`
    row the instant a Stripe intent is created (first attempt AND every
    retry). Guarantees a payments row exists for every attempt, including
    ones that later fail, before any webhook has even arrived.
  * mark_payment_failed() -- records a failed attempt via the `mark_payment_failed`
    RPC, which never downgrades a row that's already succeeded/refunded.
  * record_webhook_event() -- idempotency ledger so a retried Stripe webhook
    delivery is never processed twice.
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

    async def create_or_touch_payment_intent_record(
        self,
        order_id: str,
        user_id: Optional[str],
        pi_id: str,
        amount: float,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Eagerly writes a `payments` row the moment a PaymentIntent is
        created -- both for the first checkout attempt and for every retry
        that generates a fresh intent. This is what guarantees a payments
        row exists for every attempt, including ones that later fail, even
        before any Stripe webhook has arrived.

        `attempt_number` is assigned automatically by a DB trigger, and this
        row's insert/update is mirrored into `payment_attempts` (the
        append-only audit log) by another DB trigger -- see migration 005.
        ip_address/user_agent ride along here purely as fraud/support
        metadata; they never affect order or payment status logic.

        Non-fatal by design: if this write fails, mark_payment_failed() and
        settle_order_transaction() both INSERT ... ON CONFLICT as well, so
        a missing row here self-heals the moment Stripe sends its first
        event for this intent.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("payments").upsert(
                {
                    "order_id": order_id,
                    "user_id": user_id,
                    "stripe_payment_intent_id": pi_id,
                    "amount": amount,
                    "amount_paise": int(round(amount * 100)),
                    "currency": "INR",
                    "status": "requires_payment_method",
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
                on_conflict="stripe_payment_intent_id",
            ).execute()
        except Exception as exc:
            logger.error("DB Error creating payment record for PI %s: %s", pi_id, exc, exc_info=True)

    async def get_attempt_count(self, order_id: str) -> int:
        """
        Number of distinct PaymentIntents (attempts) already tried for this
        order -- i.e. how many rows exist in `payments` for it. Used to cap
        retries the way Amazon does: after too many failed attempts on one
        order, further retries are blocked until the abandoned-checkout
        sweep eventually cancels it, rather than letting someone hammer the
        same order indefinitely.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            res = await admin_sb.table("payments").select("id", count="exact").eq("order_id", order_id).execute()
            return getattr(res, "count", None) or 0
        except Exception as exc:
            logger.error("DB Error counting payment attempts for order %s: %s", order_id, exc, exc_info=True)
            return 0

    async def mark_payment_failed(
        self,
        order_id: str,
        user_id: Optional[str],
        pi_id: str,
        amount: float,
        reason: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """
        Records a failed attempt. Never downgrades a payments row that's
        already 'succeeded'/'refunded' -- guards against Stripe delivering
        a stale payment_failed event out of order.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.rpc("mark_payment_failed", {
                "p_order_id": order_id,
                "p_user_id": user_id,
                "p_pi_id": pi_id,
                "p_amount": amount,
                "p_reason": reason,
                "p_error_code": error_code,
            }).execute()
        except Exception as exc:
            logger.error("RPC Error marking payment %s failed: %s", pi_id, exc, exc_info=True)

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
        Idempotency ledger. Returns True the first time we see this Stripe
        event id (caller should process it), False on a duplicate delivery
        (caller should skip it -- Stripe retries webhooks on any non-2xx
        response or timeout, and can deliver the same event more than once
        even without an error on our end).

        Fails OPEN on unexpected DB errors: a hiccup in the ledger table
        should never cause us to silently drop a legitimate webhook.
        """
        admin_sb = await get_async_admin_supabase()
        try:
            await admin_sb.table("stripe_webhook_events").insert({
                "event_id": event_id,
                "event_type": event_type,
                "payment_intent_id": pi_id,
            }).execute()
            return True
        except Exception as exc:
            msg = str(exc).lower()
            if "duplicate key" in msg or "unique" in msg or "23505" in msg:
                return False
            logger.error("DB Error recording webhook event %s: %s", event_id, exc, exc_info=True)
            return True

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