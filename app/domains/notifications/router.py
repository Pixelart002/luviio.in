"""Push notification router — canonical Notifications HTTP boundary."""
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.dependencies import get_current_user, get_user_id_strict, require_permission
from app.permissions.admin import AdminPermissions
from app.domains.notifications.service import PushService
from app.domains.notifications.schemas import PushSubscription, BatchNotificationRequest
from app.constants.push_messages import PushMessages
from app.utils.response import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])
limiter = Limiter(key_func=get_remote_address)

@router.get("/vapid-key", status_code=status.HTTP_200_OK)
async def get_vapid_key(request: Request) -> Dict[str, Any]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Client requested VAPID Public Key for WebPush handshake")
    return success_response(data=PushService().get_vapid_key())

@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def subscribe(request: Request, payload: PushSubscription, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    result = await PushService().subscribe(user_id, payload.endpoint, payload.keys.p256dh, payload.keys.auth)
    return success_response(data=result, message=result["message"])

@router.delete("/unsubscribe", status_code=status.HTTP_200_OK)
async def unsubscribe(request: Request, payload: PushSubscription, current: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    await PushService().unsubscribe(payload.endpoint)
    return success_response(message=PushMessages.UNSUBSCRIBED)

@router.get("/status", status_code=status.HTTP_200_OK)
async def subscription_status(request: Request, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    return success_response(data=await PushService().get_status(user_id))

@router.post("/test", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def send_test_notification(request: Request, user_id: str = Depends(get_user_id_strict)) -> Dict[str, Any]:
    result = await PushService().send_test_notification(user_id)
    return success_response(data=result, message=getattr(PushMessages, "TEST_SENT", "Test notification dispatched"))

@router.post("/admin/send", dependencies=[Depends(require_permission(AdminPermissions.MANAGE_SETTINGS))], status_code=status.HTTP_200_OK)
async def send_batch_notification(request: Request, payload: BatchNotificationRequest) -> Dict[str, Any]:
    results = await PushService().send_batch_notification(payload.user_ids, payload.title, payload.body, payload.icon, payload.url)
    return success_response(data=results, message=PushMessages.BATCH_SENT)

@router.get("/admin/stats", dependencies=[Depends(require_permission(AdminPermissions.VIEW_ANALYTICS))], status_code=status.HTTP_200_OK)
async def push_stats(request: Request) -> Dict[str, Any]:
    return success_response(data=await PushService().get_stats())
