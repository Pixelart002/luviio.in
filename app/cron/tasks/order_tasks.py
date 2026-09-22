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
async def reconcile_checkout_payment_attempts() -> None:
    """Reconcile durable pre-provider checkout attempts that outlived their TTL."""
    from datetime import datetime, timezone

    logger.info("[CRON] Running checkout-payment-attempt reconciliation...")
    payments = __import__("app.domains.payments.repository", fromlist=["AsyncPaymentRepository"]).AsyncPaymentRepository()
    cutoff = datetime.now(timezone.utc).isoformat()
    attempts = await payments.list_stale_checkout_payment_attempts(cutoff)

    for attempt in attempts:
        attempt_id = attempt["id"]
        provider_key = str(attempt.get("payment_provider") or "").strip().lower()
        provider_payment_id = str(attempt.get("provider_payment_id") or "").strip()
        try:
            if not provider_key:
                await payments.update_checkout_payment_attempt(attempt_id, status="cancelled", last_error="missing_provider")
                continue

            provider = get_payment_provider(provider_key)
            with payment_provider_context(provider_key):
                if provider_payment_id:
                    order = await payments.get_order_by_payment_intent(provider_payment_id)
                    if order:
                        await payments.update_checkout_payment_attempt(
                            attempt_id, status="order_created", last_error=None
                        )
                        continue

                    intent = await run_in_threadpool(provider.retrieve_intent, provider_payment_id)
                    provider_status = str(intent.get("status") or "").lower()

                    if provider_status == "succeeded":
                        refunded = await run_in_threadpool(provider.process_refund, provider_payment_id)
                        if refunded:
                            await payments.update_checkout_payment_attempt(
                                attempt_id, status="completed", last_error="orphan_success_refunded"
                            )
                        else:
                            await payments.update_checkout_payment_attempt(
                                attempt_id, status="orphan_risk", last_error="orphan_success_refund_failed"
                            )
                    elif provider_status not in {"canceled", "cancelled"}:
                        await payments.update_checkout_payment_attempt(
                            attempt_id, status="cancel_requested", last_error="expired_reconciliation"
                        )
                        try:
                            await run_in_threadpool(provider.cancel_intent, provider_payment_id)
                            await payments.update_checkout_payment_attempt(
                                attempt_id, status="cancelled", last_error="expired_reconciliation"
                            )
                        except Exception as cancel_exc:
                            await payments.update_checkout_payment_attempt(
                                attempt_id, status="orphan_risk", last_error=str(cancel_exc)[:1000]
                            )
                    else:
                        await payments.update_checkout_payment_attempt(
                            attempt_id, status="cancelled", last_error="provider_already_cancelled"
                        )
                else:
                    await payments.update_checkout_payment_attempt(
                        attempt_id, status="cancelled", last_error="provider_not_created_before_expiry"
                    )
        except Exception as exc:
            logger.error(
                "[CRON] Checkout payment attempt %s reconciliation failed: %s",
                attempt_id, exc, exc_info=True,
            )

    logger.info("[CRON] Checkout-payment-attempt reconciliation complete. Checked %d attempt(s).", len(attempts))


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
        provider_key = str(order.get("payment_provider") or "").strip().lower()
        provider_payment_id = str(
            order.get("provider_payment_id") or order.get("stripe_payment_intent") or ""
        ).strip()
        customer_id = order.get("customer_id")

        try:
            if not provider_key or not provider_payment_id:
                # Repository query already excludes non-provider orders. Keep this
                # defensive guard for malformed historical rows without treating
                # them as actionable abandoned online checkouts.
                logger.warning("[CRON] Provider identity missing for pending order %s.", order_id[:8])
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
