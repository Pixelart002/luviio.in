"""
Order Cron Tasks
================
Abandoned-checkout reconciliation and stock-release sweep.

The cron layer resolves the payment provider stored on each order and never
assumes Stripe. Historical Stripe rows still work through the legacy columns.
"""
import logging

from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentRules
from app.cron.registry import cron_task
from app.domains.inventory.service import InventoryService
from app.integrations.payments.context import payment_provider_context
from app.integrations.payments.registry import get_payment_provider

logger = logging.getLogger(__name__)


@cron_task(minutes=15)
async def cleanup_abandoned_orders() -> None:
    logger.info("[CRON] Running abandoned-order sweep...")
    inventory = InventoryService()
    stale_orders = await inventory.repo.list_stale_pending_orders(
        PaymentRules.ABANDONED_ORDER_TIMEOUT_MINUTES
    )

    if not stale_orders:
        logger.info("[CRON] No abandoned orders found.")
        return

    for order in stale_orders:
        order_id = order["id"]
        provider_key = str(order.get("payment_provider") or "stripe").strip().lower()
        provider_payment_id = str(
            order.get("provider_payment_id") or order.get("stripe_payment_intent") or ""
        ).strip()
        customer_id = order.get("customer_id")

        try:
            if not provider_payment_id:
                logger.info("[CRON] Skipping non-provider pending order %s.", order_id[:8])
                continue

            provider = get_payment_provider(provider_key)
            intent = await run_in_threadpool(provider.retrieve_intent, provider_payment_id)

            with payment_provider_context(provider_key):
                if intent.get("status") == "succeeded":
                    result = await inventory.commit_reservation(
                        order_id,
                        provider_payment_id,
                        intent.get("amount", 0) / 100,
                        customer_id,
                        payment_method=(intent.get("payment_method_types") or ["card"])[0],
                        stripe_currency=intent.get("currency"),
                    )
                    logger.info(
                        "[CRON] Order %s recovered to PAID for provider %s. Result: %s",
                        order_id[:8],
                        provider_key,
                        result,
                    )
                    continue

                if intent.get("status") not in {"canceled", "cancelled"}:
                    try:
                        await run_in_threadpool(provider.cancel_intent, provider_payment_id)
                    except Exception as cancel_exc:
                        logger.warning(
                            "[CRON] Could not cancel %s payment %s: %s",
                            provider_key,
                            provider_payment_id,
                            cancel_exc,
                        )
                        refreshed = await run_in_threadpool(provider.retrieve_intent, provider_payment_id)
                        if refreshed.get("status") == "succeeded":
                            result = await inventory.commit_reservation(
                                order_id,
                                provider_payment_id,
                                refreshed.get("amount", 0) / 100,
                                customer_id,
                                payment_method=(refreshed.get("payment_method_types") or ["card"])[0],
                                stripe_currency=refreshed.get("currency"),
                            )
                            logger.info(
                                "[CRON] Order %s recovered to PAID after %s retry check. Result: %s",
                                order_id[:8],
                                provider_key,
                                result,
                            )
                            continue

                released = await inventory.release_reservation(
                    order_id,
                    reason="abandoned_checkout_timeout",
                )
                logger.info(
                    "[CRON] Order %s cancelled + stock released for provider %s. Success: %s",
                    order_id[:8],
                    provider_key,
                    released,
                )
        except Exception as exc:
            logger.error(
                "[CRON] Error processing stale order %s via %s: %s",
                order_id,
                provider_key,
                exc,
                exc_info=True,
            )

    logger.info("[CRON] Abandoned-order sweep complete. Checked %d order(s).", len(stale_orders))
