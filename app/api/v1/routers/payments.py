"""
Payments Router
===============
Path: app/api/v1/routers/payments.py
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, Response
from slowapi import Limiter

from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.payments.service import PaymentService
from app.api.schemas.payment_dto import PaymentIntentRequest, ConfirmPaymentRequest, NotifyFailedRequest
from app.utils.response import success_response

# 🔥 FIX: Use safe IP extractor for Load Balancers (like in users router)
def get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

limiter = Limiter(key_func=get_real_ip)
router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/create-intent")
@limiter.limit("10/minute")
async def create_payment_intent(
    request: Request, 
    payload: PaymentIntentRequest, 
    user_id: str = Depends(get_user_id_strict)
) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Initiating Amazon-Style AOT Checkout -> Target UID: {user_id[:8]}...")
    client_ip = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "")
    
    billing_id = str(payload.billing_address_id) if payload.billing_address_id else None
    
    data = await PaymentService().create_intent(
        user_id, 
        client_ip, 
        payload.idempotency_key, 
        str(payload.shipping_address_id),
        billing_id, # Passed down!
        user_agent=user_agent,
    )
    return success_response(data=data)

@router.post("/confirm")
@limiter.limit("10/minute")
async def confirm_payment(
    request: Request, 
    payload: ConfirmPaymentRequest, 
    current: Dict[str, Any] = Depends(get_current_user), 
    user_id: str = Depends(get_user_id_strict)
) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Verifying payment success for Intent: {payload.payment_intent_id[:10]}...")
    email = current.get("profile", {}).get("email", "")
    client_ip = get_real_ip(request)
    data = await PaymentService().confirm_payment(user_id, client_ip, payload.payment_intent_id, email)
    return success_response(data=data)

@router.post("/retry/{order_id}")
@limiter.limit("10/minute")
async def retry_payment(
    request: Request, 
    order_id: str, 
    user_id: str = Depends(get_user_id_strict)
) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Initiating Smart Paywall Retry for Order: {order_id[:8]}...")
    client_ip = get_real_ip(request)
    user_agent = request.headers.get("user-agent", "")
    data = await PaymentService().retry_payment(user_id, order_id, client_ip=client_ip, user_agent=user_agent)
    return success_response(data=data)

@router.post("/notify-failed")
async def notify_payment_failed(
    request: Request, 
    payload: NotifyFailedRequest, 
    current: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Intercepted client-side drop on Intent {payload.payment_intent_id[:10]}...")
    # 🔥 FIX: this used to be a pure no-op. Now it actually gets the failed
    # attempt into the payments table immediately (best-effort, client-
    # reported -- never touches order status; the webhook remains the
    # authoritative source of truth).
    await PaymentService().record_client_reported_failure(
        payload.payment_intent_id, payload.error_message or "Client reported failure"
    )
    return success_response(message="Failure logged. You can safely retry.")

# 🔥 NAYA WEBHOOK ENDPOINT
@router.post("/webhook")
async def stripe_webhook(request: Request):
    """Listens to Stripe Webhooks for background async state synchronization."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        return Response(content="Missing signature", status_code=400)

    try:
        await PaymentService().handle_webhook(payload, sig_header)
    except ValueError as e:
        return Response(content=str(e), status_code=400)
    except Exception as e:
        return Response(content="Internal Server Error", status_code=500)

    return Response(content="Success", status_code=200)