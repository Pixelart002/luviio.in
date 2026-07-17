"""
Push Notification Router — Async Hardened Production Grade
==========================================================
Path: app/api/v1/routers/push.py
"""
import logging
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.admin import AdminPermissions
from app.services.push.service import PushService
from app.api.schemas.push_dto import (
    PushSubscription, BatchNotificationRequest, MessageResponse, 
    VapidKeyResponse, SubscriptionStatusResponse, BatchNotificationResponse, PushStatsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])
limiter = Limiter(key_func=get_remote_address)

@router.get("/vapid-key", status_code=status.HTTP_200_OK, response_model=VapidKeyResponse)
async def get_vapid_key(request: Request):
    """Provides the VAPID Public Key for frontend Service Worker registration."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Client requested VAPID Public Key for WebPush handshake")
        
    return await PushService().get_vapid_key()

@router.post("/subscribe", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("10/minute")
async def subscribe(request: Request, payload: PushSubscription, user_id: str = Depends(get_user_id_strict)):
    """Registers client endpoint for push notifications. ABAC limits max active devices to 5."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Validating new WebPush subscription payload for UID: {user_id[:8]}...")
    
    result = await PushService().subscribe(user_id, str(payload.endpoint), payload.keys.p256dh, payload.keys.auth)
    
    if hasattr(request.state, "actions"): 
        if result.get("cleaned", 0) > 0:
            request.state.actions.append(f"Purged {result['cleaned']} stale device subscriptions")
        request.state.actions.append("Device subscription securely registered to DB ledger")
        
    return {"message": result["message"]}

@router.delete("/unsubscribe", status_code=status.HTTP_200_OK, response_model=MessageResponse)
async def unsubscribe(request: Request, payload: PushSubscription, current: dict = Depends(get_current_user)):
    """Removes specific device endpoint from the notification ledger."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Targeting active device endpoint for Push unsubscription")
    
    await PushService().unsubscribe(str(payload.endpoint))
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Subscription endpoint successfully excised from DB ledger")
        
    return {"message": "Unsubscribed successfully"}

@router.get("/status", status_code=status.HTTP_200_OK, response_model=SubscriptionStatusResponse)
async def subscription_status(request: Request, user_id: str = Depends(get_user_id_strict)):
    """Returns active device count and notification status for current user."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Evaluating active push subscriptions for UID: {user_id[:8]}...")
    
    result = await PushService().get_status(user_id)
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Found {result['subscription_count']} active devices registered")
        
    return result

@router.post(
    "/admin/send", 
    status_code=status.HTTP_200_OK, 
    dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))],
    response_model=BatchNotificationResponse
)
async def send_batch_notification(request: Request, payload: BatchNotificationRequest):
    """PBAC Guarded: Triggers manual bulk push dispatch."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"God-Mode: Admin initiating Batch Push Dispatch to {len(payload.user_ids)} target user(s)...")
    
    results = await PushService().send_batch_notification(payload.user_ids, payload.title, payload.body, payload.icon, payload.url)
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Batch dispatch completed -> Success: {results['success']} | Failed/No-Sub: {results['failed']}")
        
    return results

@router.get(
    "/admin/stats", 
    status_code=status.HTTP_200_OK, 
    dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))],
    response_model=PushStatsResponse
)
async def push_stats(request: Request):
    """PBAC Guarded: Returns global telemetry for push notification system."""
    if hasattr(request.state, "actions"): 
        request.state.actions.append("God-Mode: Admin fetching global Push telemetry")
    
    result = await PushService().get_stats()
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Aggregated {result['total_subscriptions']} total subscriptions across {result['unique_users']} unique users")
        
    return result