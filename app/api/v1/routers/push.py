"""
Push Notifications Router — Enterprise Grade
=============================================
Path: app/api/v1/routers/push.py

Architecture Upgrades:
  1. Validation schemas moved to DTOs.
  2. ALL Supabase DB logic fully delegated to PushRepository.
  3. External push delivery mapped to app.integrations.push layer.
"""
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

# 🔥 ARCHITECTURE IMPORTS
from app.core.dependencies import get_current_user, require_admin
from app.core.supabase import get_admin_supabase
from app.repositories.push_repo import PushRepository
from app.integrations.push.webpush_impl import send_push_to_user
from app.api.schemas.push_dto import (
    PushSubscription, BatchNotificationRequest, MessageResponse,
    VapidKeyResponse, SubscriptionStatusResponse, BatchNotificationResponse, PushStatsResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

# ── Rate limiter ──────────────────────────────────────────────────────────────
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

def _cleanup_stale_subscriptions(repo: PushRepository, user_id: str) -> int:
    count = repo.count_user_subscriptions(user_id)
    if count >= MAX_SUBSCRIPTIONS_PER_USER:
        to_remove = count - MAX_SUBSCRIPTIONS_PER_USER + 1
        stale_ids = repo.get_stale_subscriptions(user_id, to_remove)
        if stale_ids:
            repo.delete_subscriptions(stale_ids)
            logger.info("Cleaned %d stale subscriptions for user %.8s", len(stale_ids), user_id)
            return len(stale_ids)
    return 0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vapid-key", response_model=VapidKeyResponse)
def get_vapid_key(request: Request) -> dict[str, str]:
    if hasattr(request.state, "actions"): request.state.actions.append("Client requested VAPID Public Key")
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(status_code=503, detail="Push notifications not configured — set VAPID_PUBLIC_KEY env var")
    return {"public_key": VAPID_PUBLIC_KEY}

@router.post("/subscribe", status_code=status.HTTP_201_CREATED, response_model=MessageResponse)
@limiter.limit("10/minute")
def subscribe(request: Request, payload: PushSubscription, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = PushRepository()
    user_id = _get_user_id(current)

    if hasattr(request.state, "actions"): request.state.actions.append("Processing new push subscription request")

    if repo.is_duplicate_subscription(user_id, payload.endpoint):
        logger.debug("Push already subscribed | user=%.8s endpoint=%.40s…", user_id, payload.endpoint)
        if hasattr(request.state, "actions"): request.state.actions.append("Ignored: Device is already subscribed")
        return {"message": "Already subscribed"}

    cleaned = _cleanup_stale_subscriptions(repo, user_id)
    if hasattr(request.state, "actions") and cleaned > 0: request.state.actions.append(f"Cleaned up {cleaned} stale subscription(s)")

    if not payload.endpoint.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid push endpoint — must be HTTPS")

    sub_json = json.dumps({"endpoint": payload.endpoint, "keys": {"p256dh": payload.keys.p256dh, "auth": payload.keys.auth}})

    try:
        repo.upsert_subscription(user_id, payload.endpoint, sub_json)
        if hasattr(request.state, "actions"): request.state.actions.append("Successfully saved subscription to database")
    except Exception as e:
        logger.error("Failed to save push subscription to database: %s", e)
        raise HTTPException(status_code=500, detail="Failed to subscribe to push notifications")

    logger.info("Push subscribed | user=%.8s endpoint=%.40s… total=%d", user_id, payload.endpoint, repo.count_user_subscriptions(user_id))
    return {"message": "Subscribed successfully"}

@router.delete("/unsubscribe", response_model=MessageResponse)
def unsubscribe(request: Request, payload: PushSubscription, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, str]:
    repo = PushRepository()
    user_id = _get_user_id(current)
    
    if hasattr(request.state, "actions"): request.state.actions.append("Unsubscribe request received")
    
    try:
        deleted = repo.delete_subscription_by_endpoint(payload.endpoint)
        if hasattr(request.state, "actions"): request.state.actions.append(f"Removed {deleted} subscription(s) from database")
    except Exception as e:
        logger.error("Failed to delete push subscription: %s", e)
        raise HTTPException(status_code=500, detail="Failed to unsubscribe")
        
    logger.info("Push unsubscribed | user=%.8s deleted=%d remaining=%d", user_id, deleted, repo.count_user_subscriptions(user_id))
    return {"message": "Unsubscribed successfully"}

@router.get("/status", response_model=SubscriptionStatusResponse)
def subscription_status(request: Request, current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    repo = PushRepository()
    user_id = _get_user_id(current)
    count = repo.count_user_subscriptions(user_id)
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Checked status: {count} active subscriptions")
    
    return {"subscribed": count > 0, "subscription_count": count, "max_allowed": MAX_SUBSCRIPTIONS_PER_USER, "vapid_configured": bool(VAPID_PUBLIC_KEY)}

# ── Admin Endpoints ───────────────────────────────────────────────────────────

@router.post("/admin/send", dependencies=[Depends(require_admin)], response_model=BatchNotificationResponse)
def send_batch_notification(request: Request, payload: BatchNotificationRequest) -> dict[str, Any]:
    sb = get_admin_supabase() # Requires raw client for external integration function
    results = {"success": 0, "failed": 0, "details": []}
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Admin dispatching batch push to {len(payload.user_ids)} user(s)")
    
    for user_id in payload.user_ids:
        try:
            sent = send_push_to_user(sb_admin=sb, user_id=user_id, title=payload.title, body=payload.body, icon=payload.icon, url=payload.url)
            if sent > 0:
                results["success"] += 1; results["details"].append({"user_id": user_id, "status": "sent"})
            else:
                results["failed"] += 1; results["details"].append({"user_id": user_id, "status": "no_subscription"})
        except Exception as exc:
            results["failed"] += 1; results["details"].append({"user_id": user_id, "status": f"error: {str(exc)[:100]}"})
            logger.warning("Batch push failed for user %.8s: %s", user_id, exc)
    
    if hasattr(request.state, "actions"): request.state.actions.append(f"Push results: {results['success']} sent, {results['failed']} failed")
    logger.info("Batch push sent | success=%d failed=%d total=%d", results["success"], results["failed"], len(payload.user_ids))
    return results

@router.get("/admin/stats", dependencies=[Depends(require_admin)], response_model=PushStatsResponse)
def push_stats(request: Request) -> dict[str, Any]:
    repo = PushRepository()
    if hasattr(request.state, "actions"): request.state.actions.append("Admin requested push notification statistics")
    
    try:
        total = repo.get_total_subscriptions_count()
        unique_users = repo.get_unique_subscribed_users()
        
        return {
            "total_subscriptions": total, "unique_users": unique_users,
            "avg_per_user": round(total / unique_users, 1) if unique_users > 0 else 0,
            "vapid_configured": bool(VAPID_PUBLIC_KEY),
        }
    except Exception as exc:
        logger.error("Failed to get push stats: %s", exc)
        raise HTTPException(500, "Failed to fetch push notification statistics")