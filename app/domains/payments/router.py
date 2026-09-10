"""
Payments Router
===============
Path: app/domains/payments/router.py
"""
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_current_user, get_user_id_strict
from app.domains.orders.repository import AsyncOrderRepository
from app.domains.payments.schemas import ConfirmPaymentRequest, NotifyFailedRequest, PaymentIntentRequest
from app.domains.payments.service import PaymentService
from app.domains.payments.webhook_guard import reconcile_switched_checkout_webhook
from app.integrations.payments.registry import get_payment_provider
from app.utils.response import success_response


def get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _require_public_order_number(value: str) -> str:
    reference = str(value or "").strip()
    if not reference:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    try:
        UUID(reference)
    except (ValueError, TypeError):
        return reference
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")


async def _public_payment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    public = dict(data or {})
    internal_order_id = public.pop("order_id", None)
    if not public.get("order_number") and internal_order_id:
        order = await AsyncOrderRepository().get_order_by_id(str(internal_order_id))
        if order:
            public["order_number"] = order.get("order_number", "")
    return public


limiter = Limiter(key_func=get_real_ip)
router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-intent")
@limiter.limit("10/minute")
async def create_payment_intent(request: Request, payload: PaymentIntentRequest, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Amazon-Style AOT Checkout -> Target UID: {user_id[:8]}...")
    data = await PaymentService().create_intent(user_id, get_real_ip(request), payload.idempotency_key, str(payload.shipping_address_id), str(payload.billing_address_id) if payload.billing_address_id else None, user_agent=request.headers.get("user-agent", ""), coupon_code=payload.coupon_code)
    return success_response(data=await _public_payment_data(data))


@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: Dict[str, Any] = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying payment success for Intent: {payload.payment_intent_id[:10]}...")
    data = await PaymentService().confirm_payment(user_id, get_real_ip(request), payload.payment_intent_id, current.get("profile", {}).get("email", ""))
    return success_response(data=await _public_payment_data(data))


@router.post("/retry/{order_number}")
@limiter.limit("10/minute")
async def retry_payment(request: Request, order_number: str, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    order_number = _require_public_order_number(order_number)
    data = await PaymentService().retry_payment(user_id, order_number, client_ip=get_real_ip(request), user_agent=request.headers.get("user-agent", ""))
    return success_response(data=await _public_payment_data(data))


@router.post("/cancel/{order_number}")
@limiter.limit("10/minute")
async def cancel_checkout_payment(request: Request, order_number: str, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    order_number = _require_public_order_number(order_number)
    repo = AsyncOrderRepository()
    order = await repo.get_order_by_id(order_number)
    if not order or str(order.get("customer_id")) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    if order.get("status") != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This checkout is no longer cancellable.")

    pi_id = str(order.get("stripe_payment_intent") or "").strip()
    provider = get_payment_provider("stripe")
    if pi_id:
        try:
            intent = await run_in_threadpool(provider.retrieve_intent, pi_id)
            stripe_status = intent.get("status")
            if stripe_status == "succeeded":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already completed. This order cannot be cancelled from checkout.")
            if stripe_status not in {"canceled", "succeeded"}:
                await run_in_threadpool(provider.cancel_intent, pi_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We could not safely cancel the payment session. Please try again.") from exc

    result = await repo.cancel_order_and_restore_stock(str(order["id"]), user_id)
    if not result or result.get("status") != "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout changed while cancelling. Please retry.")
    return success_response(data={"status": "cancelled", "order_number": order_number})


@router.post("/notify-failed")
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Intercepted client-side drop on Intent {payload.payment_intent_id[:10]}...")
    await PaymentService().record_client_reported_failure(payload.payment_intent_id, payload.error_message or "Client reported failure")
    return success_response(message="Failure logged. You can safely retry.")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        return Response(content="Missing signature", status_code=400)
    try:
        provider = get_payment_provider("stripe")
        event = await run_in_threadpool(provider.verify_webhook, payload, sig_header)
        if await reconcile_switched_checkout_webhook(event):
            return Response(content="Success", status_code=200)
        await PaymentService().handle_webhook(payload, sig_header)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    except Exception:
        return Response(content="Internal Server Error", status_code=500)
    return Response(content="Success", status_code=200)
