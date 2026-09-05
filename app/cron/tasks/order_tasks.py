"""
Order Cron Tasks
================
Abandoned-checkout reconciliation and stock-release sweep.

The payment repository is owned by the payments domain. This cron module is
only an application scheduler/entrypoint and must not depend on legacy
repository paths.
"""
import logging
from datetime import datetime, timedelta, timezone

from starlette.concurrency import run_in_threadpool

from app.cron.registry import cron_task
from app.domains.payments.repository import AsyncPaymentRepository
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

                # Explicitly cancel on Stripe's side FIRST -- this prevents a
                # stale checkout tab from completing payment after stock release.
                if intent.get("status") != "canceled":
                    try:
                        await run_in_threadpool(provider.cancel_intent, pi_id)
                    except Exception as cancel_exc:
                        logger.warning(
                            "[CRON] Could not cancel Stripe intent %s (may already be closed/succeeded): %s",
                            pi_id, cancel_exc
                        )
                        # If Stripe refuses the cancel because it just
                        # succeeded, re-check instead of racing cancellation.
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