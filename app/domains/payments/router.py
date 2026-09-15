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
from app.core.supabase import get_async_admin_supabase
from app.domains.inventory.service import InventoryService
from app.domains.orders.repository import AsyncOrderRepository
from app.domains.payments.schemas import (
    ConfirmPaymentRequest,
    NotifyFailedRequest,
    PaymentIntentRequest,
)
from app.domains.payments.service import PaymentService
from app.integrations.payments.context import payment_provider_context
from app.integrations.payments.manager import PaymentPluginManager
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


async def _require_provider_enabled(provider_key: str = "stripe") -> None:
    try:
        await PaymentPluginManager().get_active_provider(provider_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


async def _public_payment_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Strip internal order UUIDs and retain the existing customer-facing order number."""
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
    provider_key = (payload.provider_key or "stripe").strip().lower()
    await _require_provider_enabled(provider_key)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating AOT Checkout -> provider: {provider_key}")
    client_ip = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "")
    billing_id = str(payload.billing_address_id) if payload.billing_address_id else None
    with payment_provider_context(provider_key):
        data = await PaymentService().create_intent(
            user_id,
            client_ip,
            payload.idempotency_key,
            str(payload.shipping_address_id),
            billing_id,
            user_agent=user_agent,
            coupon_code=payload.coupon_code,
        )
    data["payment_provider"] = provider_key
    return success_response(data=await _public_payment_data(data))


@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: Dict[str, Any] = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    provider_key = (payload.provider_key or "stripe").strip().lower()
    await _require_provider_enabled(provider_key)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Verifying provider payment: {provider_key}")
    email = current.get("profile", {}).get("email", "")
    client_ip = get_real_ip(request)
    with payment_provider_context(provider_key):
        data = await PaymentService().confirm_payment(user_id, client_ip, payload.payment_intent_id, email)
    data["payment_provider"] = provider_key
    return success_response(data=await _public_payment_data(data))


@router.post("/retry/{order_number}")
@limiter.limit("10/minute")
async def retry_payment(request: Request, order_number: str, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    order_number = _require_public_order_number(order_number)
    order_repo = AsyncOrderRepository()
    order = await order_repo.get_order_by_id(order_number)
    if not order or str(order.get("customer_id")) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    provider_key = str(order.get("payment_provider") or "stripe").strip().lower()
    await _require_provider_enabled(provider_key)
    internal_order_id = str(order["id"])
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Initiating Smart Paywall Retry -> provider: {provider_key}")
    client_ip = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "")
    with payment_provider_context(provider_key):
        data = await PaymentService().retry_payment(user_id, internal_order_id, client_ip=client_ip, user_agent=user_agent)
    data["payment_provider"] = provider_key
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

    provider_key = str(order.get("payment_provider") or "stripe").strip().lower()
    await _require_provider_enabled(provider_key)
    pi_id = str(order.get("provider_payment_id") or order.get("stripe_payment_intent") or "").strip()
    with payment_provider_context(provider_key):
        provider = await PaymentPluginManager().get_active_provider(provider_key)
        if pi_id:
            try:
                intent = await run_in_threadpool(provider.retrieve_intent, pi_id)
                provider_status = intent.get("status")
                if provider_status == "succeeded":
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already completed. This order cannot be cancelled from checkout.")
                if provider_status not in {"canceled", "succeeded"}:
                    await run_in_threadpool(provider.cancel_intent, pi_id)
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We could not safely cancel the payment session. Please try again.") from exc

    result = await InventoryService().cancel_order_with_stock_restoration(str(order["id"]), user_id)
    if not result or result.get("status") != "cancelled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout changed while cancelling. Please retry.")
    return success_response(data={"status": "cancelled", "order_number": order_number})


@router.post("/switch-method/{order_number}")
@limiter.limit("10/minute")
async def switch_pending_payment_method(request: Request, order_number: str, method: str, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    """Switch a still-pending checkout without rebuilding or restoring its cart payload."""
    order_number = _require_public_order_number(order_number)
    target = str(method or "").strip().lower()
    if target not in {"stripe", "cod"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported payment method.")

    repo = AsyncOrderRepository()
    order = await repo.get_order_by_id(order_number)
    if not order or str(order.get("customer_id")) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    if str(order.get("status") or "").lower() != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This checkout is no longer changeable.")

    current_method = str(order.get("payment_method") or "stripe").strip().lower()
    if current_method == target:
        return success_response(data={"status": "unchanged", "order_number": order_number, "payment_method": target})

    if target == "cod":
        provider_key = str(order.get("payment_provider") or "stripe").strip().lower()
        pi_id = str(order.get("provider_payment_id") or order.get("stripe_payment_intent") or "").strip()
        if pi_id:
            await _require_provider_enabled(provider_key)
            with payment_provider_context(provider_key):
                provider = await PaymentPluginManager().get_active_provider(provider_key)
                try:
                    intent = await run_in_threadpool(provider.retrieve_intent, pi_id)
                    provider_status = str(intent.get("status") or "").lower()
                    if provider_status == "succeeded":
                        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already completed. This order cannot switch payment method.")
                    if provider_status not in {"canceled", "succeeded"}:
                        await run_in_threadpool(provider.cancel_intent, pi_id)
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="We could not safely switch the payment session. Please try again.") from exc

    admin_sb = await get_async_admin_supabase()
    update = {
        "payment_method": target,
        "payment_provider": None if target == "cod" else "stripe",
        "provider_payment_id": None if target == "cod" else order.get("provider_payment_id"),
        "stripe_payment_intent": None if target == "cod" else order.get("stripe_payment_intent"),
    }
    result = await admin_sb.table("orders").update(update).eq("id", str(order["id"])).eq("customer_id", str(user_id)).eq("status", "pending").execute()
    rows = getattr(result, "data", None) or []
    if not rows:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Checkout changed while switching payment method. Please try again.")

    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Switched pending checkout payment method -> {target}")
    return success_response(data={"status": "switched", "order_number": order_number, "payment_method": target})


@router.post("/notify-failed")
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    provider_key = (payload.provider_key or "stripe").strip().lower()
    await _require_provider_enabled(provider_key)
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Intercepted client-side drop -> provider: {provider_key}")
    with payment_provider_context(provider_key):
        await PaymentService().record_client_reported_failure(payload.payment_intent_id, payload.error_message or "Client reported failure")
    return success_response(message="Failure logged. You can safely retry.")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    return await payment_webhook(request, "stripe")


@router.post("/webhook/{provider_key}")
async def payment_webhook(request: Request, provider_key: str):
    provider_key = provider_key.strip().lower()
    await _require_provider_enabled(provider_key)
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature") if provider_key == "stripe" else request.headers.get("x-payment-signature")
    if not sig_header:
        return Response(content="Missing signature", status_code=400)
    try:
        with payment_provider_context(provider_key):
            await PaymentService().handle_webhook(payload, sig_header)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    except Exception:
        return Response(content="Internal Server Error", status_code=500)
    return Response(content="Success", status_code=200)
