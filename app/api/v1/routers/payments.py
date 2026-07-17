"""
Payment Router — Async Hardened Production Grade
================================================
Path: app/api/v1/routers/payments.py
"""
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.payments.service import PaymentService
from app.api.schemas.payment_dto import PaymentIntentRequest, ConfirmPaymentRequest, NotifyFailedRequest, PaymentIntentResponse
from app.constants.payment_messages import PaymentMessages
from app.utils.response import success_response

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/create-intent", status_code=status.HTTP_200_OK, response_model=PaymentIntentResponse)
@limiter.limit("10/minute")
async def create_payment_intent(request: Request, payload: PaymentIntentRequest, user_id: str = Depends(get_user_id_strict)):
    """Initiates Amazon-Style Atomic Checkout. Automatically links cart ledger to Stripe."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Initiating Amazon-Style AOT Checkout -> Target UID: {user_id[:8]}...")
        
    return await PaymentService().create_intent(
        user_id, 
        get_remote_address(request), 
        payload.idempotency_key, 
        str(payload.shipping_address_id)
    )

@router.post("/confirm", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def confirm_payment(request: Request, payload: ConfirmPaymentRequest, current: dict = Depends(get_current_user), user_id: str = Depends(get_user_id_strict)):
    """Secures transaction confirmation. Order ID is safely extracted from Stripe Intent Metadata."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Verifying payment success for Intent: {payload.payment_intent_id[:10]}...")
        
    email = current.get("profile", {}).get("email", "")
    return success_response(await PaymentService().confirm_payment(user_id, get_remote_address(request), payload.payment_intent_id, email))

@router.post("/retry/{order_id}", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def retry_payment(request: Request, order_id: str, user_id: str = Depends(get_user_id_strict)):
    """ABAC Guarded: Regenerates or retrieves payment intent for a stalled checkout flow."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Initiating Smart Paywall Retry for Order: {order_id[:8]}...")
        
    return success_response(await PaymentService().retry_payment(user_id, order_id))

@router.post("/notify-failed", status_code=status.HTTP_200_OK)
async def notify_payment_failed(request: Request, payload: NotifyFailedRequest, current: dict = Depends(get_current_user)):
    """Logs client-side payment drops without modifying atomic database states."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Intercepted client-side drop on Intent {payload.payment_intent_id[:10]}...")
        
    return success_response(message=PaymentMessages.FAILURE_LOGGED)