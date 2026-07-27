"""
Payments Router
===============
Path: app/api/v1/routers/payments.py
"""
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict
from app.services.payments.service import PaymentService
from app.api.schemas.payment_dto import PaymentIntentRequest, ConfirmPaymentRequest, NotifyFailedRequest
from app.utils.response import success_response

limiter = Limiter(key_func=get_remote_address)
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
    client_ip = get_remote_address(request) or "0.0.0.0"
    data = await PaymentService().create_intent(user_id, client_ip, payload.idempotency_key, str(payload.shipping_address_id))
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
    client_ip = get_remote_address(request) or "0.0.0.0"
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
    data = await PaymentService().retry_payment(user_id, order_id)
    return success_response(data=data)

@router.post("/notify-failed")
async def notify_payment_failed(
    request: Request, 
    payload: NotifyFailedRequest, 
    current: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Intercepted client-side drop on Intent {payload.payment_intent_id[:10]}...")
    return success_response(message="Failure logged. User can safely retry.")