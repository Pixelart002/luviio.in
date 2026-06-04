"""
Push Notifications Router — Production Grade
=============================================
Features & Fixes:
  1. POSTGREST 406 FIX: Used .limit(1).execute() for counts.
  2. MEMORY LEAK FIX: Exact counts no longer download full table rows.
  3. STALE CLEANUP FIX: Replaced invalid asc=True with desc=False.
  4. SECURITY: Strict rate limiting and duplicate subscription prevention.
  5. NEW: Pure Window Logger integration for clear terminal tracking.
  6. FIX: Suppressed spammy "Already subscribed" logs (changed to debug).
"""
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.dependencies import get_current_user, require_admin
from app.supabase_client import get_admin_supabase
from app.utils.push import send_push_to_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_SUBSCRIPTIONS_PER_USER = 5

# ── Models ────────────────────────────────────────────────────────────────────

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys

class BatchNotificationRequest(BaseModel):
    user_ids: list[str]
    title: str = "Luviio"
    body: str
    icon: str = "/icons/ri-notification-3-line.png"
    url: str = "/"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in session keys: {list(current_user.keys())}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, 
        detail="User ID not found in session"
    )


def _count_user_subscriptions(sb: Any, user_id: str) -> int:
    try:
        res = (
            sb.table("push_subscriptions")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return res.count if res and hasattr(res, "count") and res.count else 0
    except Exception as exc:
        logger.warning("Failed to count subscriptions for user %.8s: %s", user_id, exc)
        return 0


def _cleanup_stale_subscriptions(sb: Any, user_id: str) -> int:
    try:
        count = _count_user_subscriptions(sb, user_id)
        if count >= MAX_SUBSCRIPTIONS_PER_USER:
            to_remove = count - MAX_SUBSCRIPTIONS_PER_USER + 1
            old = (
                sb.table("push_subscriptions")
                .select("id")
                .eq("user_id", user_id)
                .order("created_at", desc=False) 
                .limit(to_remove)
                .execute()
            )
            if old and hasattr(old, "data") and old.data:
                ids = [row["id"] for row in old.data]
                sb.table("push_subscriptions").delete().in_("id", ids).execute()
                logger.info("Cleaned %d stale subscriptions for user %.8s", len(ids), user_id)
                return len(ids)
    except Exception as exc:
        logger.warning("Subscription cleanup failed for user %.8s: %s", user_id, exc)
    return 0


def _is_duplicate_subscription(sb: Any, endpoint: str, user_id: str) -> bool:
    try:
        existing = (
            sb.table("push_subscriptions")
            .select("id")
            .eq("endpoint", endpoint)
            .eq("user_id", user_id)
            .limit(1) 
            .execute()
        )
        return bool(existing and hasattr(existing, "data") and existing.data)
    except Exception:
        return False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vapid-key")
def get_vapid_key(request: Request) -> dict[str, str]:
    if hasattr(request.state, "actions"):
        request.state.actions.append("Client requested VAPID Public Key")
        
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications not configured — set VAPID_PUBLIC_KEY env var",
        )
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def subscribe(
    request: Request,
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    user_id = _get_user_id(current)

    if hasattr(request.state, "actions"):
        request.state.actions.append("Processing new push subscription request")

    if _is_duplicate_subscription(sb, payload.endpoint, user_id):
        # [FIX] Changed to debug to avoid terminal spam
        logger.debug(
            "Push already subscribed | user=%.8s endpoint=%.40s…", 
            user_id, payload.endpoint
        )
        if hasattr(request.state, "actions"):
            request.state.actions.append("Ignored: Device is already subscribed")
        return {"message": "Already subscribed"}

    cleaned = _cleanup_stale_subscriptions(sb, user_id)
    if hasattr(request.state, "actions") and cleaned > 0:
        request.state.actions.append(f"Cleaned up {cleaned} stale subscription(s)")

    if not payload.endpoint.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid push endpoint — must be HTTPS",
        )

    sub_json = json.dumps({
        "endpoint": payload.endpoint,
        "keys": {
            "p256dh": payload.keys.p256dh,
            "auth": payload.keys.auth,
        },
    })

    try:
        sb.table("push_subscriptions").upsert(
            {
                "endpoint": payload.endpoint,
                "user_id": user_id,
                "subscription_json": sub_json,
            },
            on_conflict="endpoint",
        ).execute()
        
        if hasattr(request.state, "actions"):
            request.state.actions.append("Successfully saved subscription to database")
            
    except Exception as e:
        logger.error("Failed to save push subscription to database: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to push notifications"
        )

    logger.info(
        "Push subscribed | user=%.8s endpoint=%.40s… total=%d",
        user_id, payload.endpoint, _count_user_subscriptions(sb, user_id)
    )
    return {"message": "Subscribed successfully"}


@router.delete("/unsubscribe")
def unsubscribe(
    request: Request,
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Unsubscribe request received")
    
    try:
        result = (
            sb.table("push_subscriptions")
            .delete()
            .eq("endpoint", payload.endpoint)
            .execute()
        )
        deleted = len(result.data) if result and hasattr(result, "data") and result.data else 0
        
        if hasattr(request.state, "actions"):
            request.state.actions.append(f"Removed {deleted} subscription(s) from database")
            
    except Exception as e:
        logger.error("Failed to delete push subscription: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsubscribe"
        )
        
    logger.info(
        "Push unsubscribed | user=%.8s deleted=%d remaining=%d",
        user_id, deleted, _count_user_subscriptions(sb, user_id)
    )
    return {"message": "Unsubscribed successfully"}


@router.get("/status")
def subscription_status(
    request: Request,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    sb = get_admin_supabase()
    user_id = _get_user_id(current)
    count = _count_user_subscriptions(sb, user_id)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Checked status: {count} active subscriptions")
    
    return {
        "subscribed": count > 0,
        "subscription_count": count,
        "max_allowed": MAX_SUBSCRIPTIONS_PER_USER,
        "vapid_configured": bool(VAPID_PUBLIC_KEY),
    }


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@router.post("/admin/send", dependencies=[Depends(require_admin)])
def send_batch_notification(
    request: Request,
    payload: BatchNotificationRequest,
) -> dict[str, Any]:
    sb = get_admin_supabase()
    results = {"success": 0, "failed": 0, "details": []}
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Admin dispatching batch push to {len(payload.user_ids)} user(s)")
    
    for user_id in payload.user_ids:
        try:
            sent = send_push_to_user(
                sb_admin=sb,
                user_id=user_id,
                title=payload.title,
                body=payload.body,
                icon=payload.icon,
                url=payload.url,
            )
            if sent > 0:
                results["success"] += 1
                results["details"].append({"user_id": user_id, "status": "sent"})
            else:
                results["failed"] += 1
                results["details"].append({"user_id": user_id, "status": "no_subscription"})
        except Exception as exc:
            results["failed"] += 1
            results["details"].append({"user_id": user_id, "status": f"error: {str(exc)[:100]}"})
            logger.warning("Batch push failed for user %.8s: %s", user_id, exc)
    
    if hasattr(request.state, "actions"):
        request.state.actions.append(f"Push results: {results['success']} sent, {results['failed']} failed")
        
    logger.info(
        "Batch push sent | success=%d failed=%d total=%d",
        results["success"], results["failed"], len(payload.user_ids)
    )
    return results


@router.get("/admin/stats", dependencies=[Depends(require_admin)])
def push_stats(request: Request) -> dict[str, Any]:
    sb = get_admin_supabase()
    
    if hasattr(request.state, "actions"):
        request.state.actions.append("Admin requested push notification statistics")
    
    try:
        total_res = (
            sb.table("push_subscriptions")
            .select("id", count="exact")
            .limit(1)  
            .execute()
        )
        total = total_res.count if total_res and hasattr(total_res, "count") and total_res.count else 0
        
        unique_res = (
            sb.table("push_subscriptions")
            .select("user_id")
            .execute()
        )
        
        unique_users = len(set(row["user_id"] for row in (getattr(unique_res, "data", None) or [])))
        
        return {
            "total_subscriptions": total,
            "unique_users": unique_users,
            "avg_per_user": round(total / unique_users, 1) if unique_users > 0 else 0,
            "vapid_configured": bool(VAPID_PUBLIC_KEY),
        }
    except Exception as exc:
        logger.error("Failed to get push stats: %s", exc)
        raise HTTPException(500, "Failed to fetch push notification statistics")
