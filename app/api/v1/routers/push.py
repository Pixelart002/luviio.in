"""
Push Notifications Router — Async Enterprise Grade
==================================================
Path: app/api/v1/routers/push.py
"""
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.concurrency import run_in_threadpool

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.core.supabase import get_admin_supabase
from app.repositories.push_repo import AsyncPushRepository
from app.integrations.push.webpush_impl import send_push_to_user
from app.api.schemas.push_dto import (
    PushSubscription, BatchNotificationRequest, MessageResponse,
    VapidKeyResponse, SubscriptionStatusResponse, BatchNotificationResponse, PushStatsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

limiter = Limiter(key_func=get_remote_address)
MAX_SUBSCRIPTIONS_PER_USER = 5

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user: return str(current_user["id"])
    if "sub" in current_user: return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in session keys: {list(current_user.keys())}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")

async def _cleanup_stale_subscriptions(repo: AsyncPushRepository, user_id: str) -> int:
    count = await repo.count_user_subscriptions(user_id)
    if count >= MAX_SUBSCRIPTIONS_PER_USER:
        to_remove = count - MAX_SUBSCRIPTIONS_PER_USER + 1
        stale_ids = await repo.get_stale_subscriptions(user_id, to_remove)
        if stale_ids:
            await repo.delete_subscriptions(stale_ids)
            logger.info("Cleaned %d stale subscriptions for user %.8s", len(stale_ids), user_id)
            return len(stale_ids)
    return 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_key(request: Request) -> dict[str, str]:
    if hasattr(request.state, "actions"): request.state.actions.append("Client requested VAPID Public Key")
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"public_key": VAPID_PUBLIC_KEY}

@router.post("/subscribe", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("10/minute")
async def subscribe(request: Request, payload: PushSubscription, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = AsyncPushRepository()
    user_id = _get_user_id(current)

    if await repo.is_duplicate_subscription(user_id, payload.endpoint):
        return {"message": "Already subscribed"}

    await _cleanup_stale_subscriptions(repo, user_id)

    if not payload.endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid push endpoint — must be HTTPS")

    sub_json = json.dumps({"endpoint": payload.endpoint, "keys": {"p256dh": payload.keys.p256dh, "auth": payload.keys.auth}})

    try:
        await repo.upsert_subscription(user_id, payload.endpoint, sub_json)
    except Exception as e:
        logger.error("Failed to save push subscription to database: %s", e)
        raise HTTPException(status_code=500, detail="Failed to subscribe to push notifications")

    return {"message": "Subscribed successfully"}

@router.delete("/unsubscribe", response_model=MessageResponse)
async def unsubscribe(request: Request, payload: PushSubscription, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = AsyncPushRepository()
    try:
        await repo.delete_subscription_by_endpoint(payload.endpoint)
    except Exception as e:
        logger.error("Failed to delete push subscription: %s", e)
        raise HTTPException(status_code=500, detail="Failed to unsubscribe")
        
    return {"message": "Unsubscribed successfully"}

@router.get("/status", response_model=SubscriptionStatusResponse)
async def subscription_status(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = AsyncPushRepository()
    user_id = _get_user_id(current)
    count = await repo.count_user_subscriptions(user_id)
    return {"subscribed": count > 0, "subscription_count": count, "max_allowed": MAX_SUBSCRIPTIONS_PER_USER, "vapid_configured": bool(VAPID_PUBLIC_KEY)}

# ── Admin Endpoints ───────────────────────────────────────────────────────────

@router.post("/admin/send", dependencies=[Depends(require_admin)], response_model=BatchNotificationResponse)
async def send_batch_notification(request: Request, payload: BatchNotificationRequest) -> dict[str, Any]:
    sb = get_admin_supabase() # Requires raw sync client for external integration function
    results = {"success": 0, "failed": 0, "details": []}
    
    for user_id in payload.user_ids:
        try:
            # Offloading external API calls to a threadpool to prevent blocking the async loop
            sent = await run_in_threadpool(send_push_to_user, sb_admin=sb, user_id=user_id, title=payload.title, body=payload.body, icon=payload.icon, url=payload.url)
            if sent > 0:
                results["success"] += 1; results["details"].append({"user_id": user_id, "status": "sent"})
            else:
                results["failed"] += 1; results["details"].append({"user_id": user_id, "status": "no_subscription"})
        except Exception as exc:
            results["failed"] += 1; results["details"].append({"user_id": user_id, "status": f"error: {str(exc)[:100]}"})
    
    return results

@router.get("/admin/stats", dependencies=[Depends(require_admin)], response_model=PushStatsResponse)
async def push_stats(request: Request) -> dict[str, Any]:
    repo = AsyncPushRepository()
    try:
        total = await repo.get_total_subscriptions_count()
        unique_users = await repo.get_unique_subscribed_users()
        return {
            "total_subscriptions": total, "unique_users": unique_users,
            "avg_per_user": round(total / unique_users, 1) if unique_users > 0 else 0,
            "vapid_configured": bool(VAPID_PUBLIC_KEY),
        }
    except Exception as exc:
        raise HTTPException(500, "Failed to fetch push notification statistics")