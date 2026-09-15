"""
Order Cron Tasks
================
Abandoned-checkout reconciliation and stock-release sweep.

This cron module is an application scheduler/entrypoint. Inventory owns stock
reservation release and payment settlement.
"""
import logging
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentRules
from app.cron.registry import cron_task
from app.domains.inventory.service import InventoryService
from app.integrations.payments.registry import get_payment_provider

logger = logging.getLogger(__name__)


@cron_task(minutes=15)
async def cleanup_abandoned_orders() -> None:
    logger.info("[CRON] Running abandoned-order sweep...")
    inventory = InventoryService()
    provider = get_payment_provider("stripe")

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=PaymentRules.ABANDONED_ORDER_TIMEOUT_MINUTES)
    stale_orders = await inventory.repo.list_stale_pending_orders(
        PaymentRules.ABANDONED_ORDER_TIMEOUT_MINUTES
    )

    if not stale_orders:
        logger.info("[CRON] No abandoned orders found.")
        return

    for order in stale_orders:
        order_id = order["id"]
        pi_id = order.get("stripe_payment_intent")
        customer_id = order.get("customer_id")
        try:
            if not pi_id:
                logger.info("[CRON] Skipping COD/non-Stripe pending order %s.", order_id[:8])
                continue
            intent = await run_in_threadpool(provider.retrieve_intent, pi_id)
            if intent.get("status") == "succeeded":
                result = await inventory.commit_reservation(
                    order_id, pi_id, intent.get("amount", 0) / 100, customer_id,
                    payment_method=(intent.get("payment_method_types") or ["card"])[0],
                    stripe_currency=intent.get("currency"),
                )
                logger.info("[CRON] Order %s recovered to PAID (missed webhook). Result: %s", order_id[:8], result)
                continue
            if intent.get("status") != "canceled":
                try:
                    await run_in_threadpool(provider.cancel_intent, pi_id)
                except Exception as cancel_exc:
                    logger.warning("[CRON] Could not cancel Stripe intent %s: %s", pi_id, cancel_exc)
                    refreshed = await run_in_threadpool(provider.retrieve_intent, pi_id)
                    if refreshed.get("status") == "succeeded":
                        result = await inventory.commit_reservation(
                            order_id, pi_id, refreshed.get("amount", 0) / 100, customer_id,
                            payment_method=(refreshed.get("payment_method_types") or ["card"])[0],
                            stripe_currency=refreshed.get("currency"),
                        )
                        logger.info("[CRON] Order %s recovered to PAID on retry check. Result: %s", order_id[:8], result)
                        continue
            released = await inventory.release_reservation(order_id, reason="abandoned_checkout_timeout")
            logger.info("[CRON] Order %s cancelled + stock released. Success: %s", order_id[:8], released)
        except Exception as exc:
            logger.error("[CRON] Error processing stale order %s: %s", order_id, exc, exc_info=True)

    logger.info("[CRON] Abandoned-order sweep complete. Checked %d order(s).", len(stale_orders))
