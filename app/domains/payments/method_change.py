"""Controlled payment-method change for exhausted card retries.

Sensitive payment credentials never pass through Luviio. Stripe Payment Element
collects them directly. This module only handles Stripe PaymentIntent IDs,
method type, and durable payment-attempt accounting.
"""
import logging
import time
from typing import Any, Dict

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.constants.payment_messages import PaymentRules, PaymentSecurityMessages
from app.core.supabase import get_async_admin_supabase
from app.domains.payments.repository import AsyncPaymentRepository
from app.integrations.payments.registry import get_payment_provider

logger = logging.getLogger(__name__)
_ALLOWED_METHODS = {"upi", "netbanking"}


class PaymentMethodChangeService:
    def __init__(self) -> None:
        self.repo = AsyncPaymentRepository()
        self.provider = get_payment_provider("stripe")

    async def change_method(self, user_id: str, order_id: str, new_payment_method: str) -> Dict[str, Any]:
        method = str(new_payment_method or "").strip().lower()
        if method not in _ALLOWED_METHODS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a supported alternative payment method.")

        order = await self.repo.get_order_by_id(order_id)
        if not order or str(order.get("customer_id")) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        if order.get("status") != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This order is no longer payable.")

        old_pi_id = str(order.get("stripe_payment_intent") or "").strip()
        if not old_pi_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No active payment session is available to change.")

        try:
            old_intent = await run_in_threadpool(self.provider.retrieve_intent, old_pi_id)
            if old_intent.get("status") == "succeeded":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already completed.")
            if old_intent.get("status") != "canceled":
                await run_in_threadpool(self.provider.cancel_intent, old_pi_id)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[PAYMENT METHOD CHANGE] Could not retire old PI for order %s", order_id[:8], exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We could not safely change the payment method. Please try again.") from exc

        amount_paise = int(round(float(order.get("total_amount") or 0) * 100))
        if amount_paise < PaymentRules.MIN_ORDER_AMOUNT_PAISE:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=PaymentSecurityMessages.ZERO_AMOUNT_RETRY)

        try:
            new_intent = await run_in_threadpool(
                self.provider.create_payment_intent,
                amount_paise,
                "inr",
                "AOT_METHOD_CHANGE",
                user_id,
                f"method_change_{order_id}_{method}_{time.time_ns()}",
                [method],
            )
        except Exception as exc:
            logger.error("[PAYMENT METHOD CHANGE] Stripe replacement creation failed", exc_info=True)
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED) from exc

        new_pi_id = str(new_intent.get("id") or "").strip()
        if not new_pi_id:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=PaymentSecurityMessages.PAYMENT_FAILED)

        try:
            admin_sb = await get_async_admin_supabase()
            res = await admin_sb.rpc(
                "change_payment_method_after_limit",
                {
                    "p_order_id": order_id,
                    "p_user_id": user_id,
                    "p_old_pi_id": old_pi_id,
                    "p_new_pi_id": new_pi_id,
                    "p_new_payment_method": method,
                    "p_max_attempts": PaymentRules.BRUTE_FORCE_MAX_ATTEMPTS,
                },
            ).execute()
            data = getattr(res, "data", None)
            row = data[0] if isinstance(data, list) and data else data
            if not row:
                raise RuntimeError("Payment method change RPC returned no data")
        except Exception as exc:
            try:
                await run_in_threadpool(self.provider.cancel_intent, new_pi_id)
            except Exception:
                logger.error("[PAYMENT METHOD CHANGE] Failed to cancel unlinked replacement PI", exc_info=True)
            message = str(exc)
            if "PAYMENT_METHOD_CHANGE_NOT_REQUIRED" in message:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment method change is available after the card retry limit is reached.") from exc
            if "PAYMENT_METHOD_ALREADY_USED" in message:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This payment method has already been tried for this order.") from exc
            if "UNSUPPORTED_PAYMENT_METHOD" in message:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a supported alternative payment method.") from exc
            if "ORDER_NO_LONGER_RETRYABLE" in message or "ORDER_CHANGED_DURING_PAYMENT_METHOD_CHANGE" in message:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PaymentSecurityMessages.ORDER_NO_LONGER_RETRYABLE) from exc
            logger.error("[PAYMENT METHOD CHANGE] Atomic DB swap failed", exc_info=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to change payment method safely. Please try again.") from exc

        await run_in_threadpool(self.provider.update_intent_metadata, new_pi_id, {"order_id": order_id, "user_id": user_id, "payment_method_change": "true"})
        return {
            "client_secret": new_intent.get("client_secret"),
            "payment_intent_id": new_pi_id,
            "order_id": order_id,
            "payment_method": method,
            "attempt_number": int(row.get("attempt_number")),
        }
