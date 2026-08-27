"""
Order Cron Tasks
================
Path: app/cron/tasks/order_tasks.py

🔥 FIX (Problem 3 / Scenario C -- abandoned checkout):
This job was previously commented out entirely, so a 'pending' order with
no successful payment (browser closed, webhook dropped, network died mid-
checkout) stayed 'pending' forever with its stock reserved indefinitely.

Runs every 15 minutes. For every order that has been 'pending' for longer
than PaymentRules.ABANDONED_ORDER_TIMEOUT_MINUTES:
  1. Re-checks the PaymentIntent directly with Stripe first (self-healing --
     covers the case where the success webhook itself was the thing that
     got dropped).
  2. If it actually succeeded -> settle the order now.
  3. Otherwise -> explicitly CANCEL the PaymentIntent on Stripe (so a stale
     browser tab can never complete payment after this point), then cancel
     the order and release its reserved stock via the atomic RPC.

This is the ONLY place (besides an explicit `payment_intent.canceled`
webhook) that should ever cancel a 'pending' order over a failed payment --
a single card decline must NOT cancel the order; see payments/service.py.
"""
import logging
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool

from app.cron.registry import cron_task
from app.repositories.payment_repo import AsyncPaymentRepository
from app.integrations.payments.registry import get_payment_provider
from app.constants.payment_messages import PaymentRules

logger = logging.getLogger(__name__)


@cron_task(minutes=15)
async def cleanup_abandoned_orders() -> None:
    logger.info("[CRON] Running abandoned-order sweep...")
    repo = AsyncPaymentRepository()
    provider = get_payment_provider("stripe")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PaymentRules.ABANDONED_ORDER_TIMEOUT_MINUTES)
    stale_orders = await repo.list_stale_pending_orders(cutoff.isoformat())

    if stale_orders is None:
        logger.warning("[CRON] Abandoned-order sweep skipped: could not reach database.")
        return

    if not stale_orders:
        logger.info("[CRON] No abandoned orders found.")
        return

    for order in stale_orders:
        order_id = order["id"]
        pi_id = order.get("stripe_payment_intent")
        customer_id = order.get("customer_id")

        try:
            if pi_id:
                intent = await run_in_threadpool(provider.retrieve_intent, pi_id)

                # Self-heal: the success webhook may have been the thing
                # that got lost, not the payment itself.
                if intent.get("status") == "succeeded":
                    result = await repo.settle_order_transaction(
                        order_id, pi_id, intent.get("amount", 0) / 100, customer_id
                    )
                    logger.info("[CRON] Order %s recovered to PAID (missed webhook). Result: %s", order_id[:8], result)
                    continue

                # Explicitly cancel on Stripe's side FIRST -- this is what
                # prevents a customer's stale checkout tab from completing
                # payment on this intent after we've released the stock.
                if intent.get("status") != "canceled":
                    try:
                        await run_in_threadpool(provider.cancel_intent, pi_id)
                    except Exception as cancel_exc:
                        logger.warning(
                            "[CRON] Could not cancel Stripe intent %s (may already be closed/succeeded): %s",
                            pi_id, cancel_exc
                        )
                        # If Stripe refuses the cancel because it just
                        # succeeded, don't proceed to cancel the order --
                        # re-check on the next sweep instead of racing it.
                        refreshed = await run_in_threadpool(provider.retrieve_intent, pi_id)
                        if refreshed.get("status") == "succeeded":
                            result = await repo.settle_order_transaction(
                                order_id, pi_id, refreshed.get("amount", 0) / 100, customer_id
                            )
                            logger.info("[CRON] Order %s recovered to PAID on retry check. Result: %s", order_id[:8], result)
                            continue

            result = await repo.release_abandoned_order(order_id, reason="abandoned_checkout_timeout")
            logger.info("[CRON] Order %s cancelled + stock released. Result: %s", order_id[:8], result)

        except Exception as e:
            logger.error("[CRON] Error processing stale order %s: %s", order_id, e, exc_info=True)

    logger.info("[CRON] Abandoned-order sweep complete. Checked %d order(s).", len(stale_orders))