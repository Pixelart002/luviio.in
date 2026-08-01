"""
Push Router — Async Standardized Endpoints
==========================================
Path: app/api/v1/routers/push.py
"""
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.admin import AdminPermissions
from app.services.notifications.push import PushService
from app.api.schemas.push_dto import PushSubscription, BatchNotificationRequest
from app.constants.push_messages import PushMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])
limiter = Limiter(key_func=get_remote_address)

@router.get("/vapid-key", status_code=status.HTTP_200_OK)
async def get_vapid_key(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Client requested VAPID Public Key for WebPush handshake")
    data = PushService().get_vapid_key()
    return success_response(data=data)

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def subscribe(request: Request, payload: PushSubscription, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Validating new WebPush subscription payload for UID: {user_id[:8]}...")
    
    result = await PushService().subscribe(user_id, payload.endpoint, payload.keys.p256dh, payload.keys.auth)
    
    if hasattr(request.state, "actions"): 
        if result.get("cleaned", 0) > 0:
            request.state.actions.append(f"Purged {result['cleaned']} stale device subscriptions")
        request.state.actions.append("Device subscription securely registered to DB ledger")
        
    return success_response(data=result, message=result["message"])

@router.delete("/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe(request: Request, payload: PushSubscription, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Targeting active device endpoint for Push unsubscription")
    
    await PushService().unsubscribe(payload.endpoint)
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append("Subscription endpoint successfully excised from DB ledger")
        
    return success_response(message=PushMessages.UNSUBSCRIBED)

@router.get("/status", status_code=status.HTTP_200_OK)
async def subscription_status(request: Request, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Evaluating active push subscriptions for UID: {user_id[:8]}...")
    
    result = await PushService().get_status(user_id)
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Found {result['subscription_count']} active devices registered")
        
    return success_response(data=result)

@router.post("/admin/send", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))], status_code=status.HTTP_200_OK)
async def send_batch_notification(request: Request, payload: BatchNotificationRequest) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"God-Mode: Admin initiating Batch Push Dispatch to {len(payload.user_ids)} target user(s)...")
    
    results = await PushService().send_batch_notification(payload.user_ids, payload.title, payload.body, payload.icon, payload.url)
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Batch dispatch completed -> Success: {results['success']} | Failed/No-Sub: {results['failed']}")
        
    return success_response(data=results, message=PushMessages.BATCH_SENT)

@router.get("/admin/stats", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
async def push_stats(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"): 
        request.state.actions.append("God-Mode: Admin fetching global Push telemetry")
    
    result = await PushService().get_stats()
    
    if hasattr(request.state, "actions"): 
        request.state.actions.append(f"Aggregated {result['total_subscriptions']} total subscriptions across {result['unique_users']} unique users")
        
    return success_response(data=result)