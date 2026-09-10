"""Webhook reconciliation guard for payment-method switches.

A customer can start Stripe, then switch the same pending checkout to COD.
The Stripe attempt remains historical telemetry, but a late Stripe success must
never turn the COD order into an online-paid order or create double revenue.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from app.core.supabase import get_async_admin_supabase
from app.integrations.payments.registry import get_payment_provider

logger = logging.getLogger(__name__)


async def reconcile_switched_checkout_webhook(event: dict[str, Any]) -> bool:
    """Handle a late success for a Stripe attempt detached by a COD switch.

    Returns True only when this guard fully owns the webhook event. Other events
    continue through the normal PaymentService webhook pipeline.
    """
    event_type = event.get("type")
    if event_type != "payment_intent.succeeded":
        return False

    obj = event.get("data", {}).get("object", {}) or {}
    pi_id = obj.get("id") if obj.get("object") == "payment_intent" else obj.get("payment_intent")
    if not pi_id:
        return False

    sb = await get_async_admin_supabase()
    attempt_res = await (
        sb.table("payment_attempts")
        .select("order_id,user_id,status")
        .eq("stripe_payment_intent_id", pi_id)
        .maybe_single()
        .execute()
    )
    attempt = getattr(attempt_res, "data", None)
    if not attempt or not attempt.get("order_id"):
        return False

    order_res = await (
        sb.table("orders")
        .select("id,customer_id,status,payment_method,stripe_payment_intent,total_amount")
        .eq("id", attempt["order_id"])
        .maybe_single()
        .execute()
    order = getattr(order_res, "data", None)
    if not order:
        return False

    # Only the Stripe -> COD switch path is special. A normal Stripe order is
    # handled by PaymentService as usual.
    if order.get("status") != "pending" or order.get("payment_method") != "cod" or order.get("stripe_payment_intent") is not None:
        return False

    event_id = event.get("id")
    if event_id:
        claimed = await sb.rpc("claim_webhook_event", {"p_event_id": event_id, "p_event_type": event_type, "p_pi_id": pi_id}).execute()
        if getattr(claimed, "data", None) is False:
            return True

    provider = get_payment_provider("stripe")
    try:
        await run_in_threadpool(provider.process_refund, pi_id)
    except Exception:
        logger.error("[WEBHOOK GUARD] Late Stripe success could not be refunded for COD order %s / PI %s", order.get("id", "")[:8], pi_id, exc_info=True)
        raise

    await (
        sb.table("payment_attempts")
        .update({"status": "orphaned_success", "error_message": "Stripe succeeded after checkout was switched to COD; refund initiated."})
        .eq("stripe_payment_intent_id", pi_id)
        .execute()
    )
    await (
        sb.table("payments")
        .update({"status": "pending", "payment_method": "cod", "error_code": "LATE_STRIPE_SUCCESS", "error_message": "Late Stripe success refunded after COD switch."})
        .eq("order_id", order["id"])
        .execute()
    )
    if event_id:
        await sb.rpc("mark_webhook_event_processed", {"p_event_id": event_id}).execute()
    logger.warning("[WEBHOOK GUARD] Refunded late Stripe success %s for COD order %s", pi_id, order.get("id"))
    return True
