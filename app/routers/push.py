"""
Push Notifications Router
=========================
Changes from original:
  1. FIXED: Replaced unsafe current["profile"]["id"] with robust _get_user_id()
  2. FIXED: Added try-except blocks around Supabase operations to prevent unhandled 500 crashes
"""
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/push", tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")


# ── Models ────────────────────────────────────────────────────────────────────

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_user_id(current_user: dict[str, Any]) -> str:
    """Safely extract user_id from the current user object/token payload."""
    if "profile" in current_user and isinstance(current_user["profile"], dict) and "id" in current_user["profile"]:
        return str(current_user["profile"]["id"])
    if "id" in current_user:
        return str(current_user["id"])
    if "sub" in current_user:
        return str(current_user["sub"])
        
    logger.error(f"Cannot find user ID in: {current_user}")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in session")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/vapid-key")
def get_vapid_key() -> dict[str, str]:
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications not configured — set VAPID_PUBLIC_KEY env var",
        )
    return {"public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    
    # [FIX 1] Safely get user ID to prevent KeyError
    user_id = _get_user_id(current)

    sub_json = json.dumps({
        "endpoint": payload.endpoint,
        "keys": {
            "p256dh": payload.keys.p256dh,
            "auth": payload.keys.auth,
        },
    })

    # [FIX 2] Prevent crash if database upsert fails
    try:
        sb.table("push_subscriptions").upsert(
            {
                "endpoint": payload.endpoint,
                "user_id": user_id,
                "subscription_json": sub_json,
            },
            on_conflict="endpoint",
        ).execute()
    except Exception as e:
        logger.error("Failed to save push subscription to database: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to subscribe to push notifications"
        )

    logger.info("Push subscribed | user=%s endpoint=%.40s…", user_id, payload.endpoint)
    return {"message": "Subscribed successfully"}


@router.delete("/unsubscribe")
def unsubscribe(
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    
    # [FIX 1] Safely get user ID
    user_id = _get_user_id(current)
    
    # [FIX 2] Prevent crash if database delete fails
    try:
        sb.table("push_subscriptions").delete().eq("endpoint", payload.endpoint).execute()
    except Exception as e:
        logger.error("Failed to delete push subscription: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsubscribe"
        )
        
    logger.info("Push unsubscribed | user=%s", user_id)
    return {"message": "Unsubscribed successfully"}