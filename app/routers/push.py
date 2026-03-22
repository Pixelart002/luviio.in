"""
Push Notifications Router — /api/v1/push
==========================================
Endpoints:
  GET  /push/vapid-key      → frontend gets public key to subscribe
  POST /push/subscribe      → save subscription to DB
  DELETE /push/unsubscribe  → remove subscription
"""
import json
import logging
import os
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.supabase_client import get_admin_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/push", tags=["Push Notifications"])

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth:   str


class PushSubscription(BaseModel):
    endpoint: str
    keys:     SubscriptionKeys


# ── GET vapid public key — frontend needs this to subscribe ──────────────────
@router.get("/vapid-key")
def get_vapid_key() -> dict[str, str]:
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Push notifications not configured",
        )
    return {"public_key": VAPID_PUBLIC_KEY}


# ── POST subscribe — save subscription ───────────────────────────────────────
@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb      = get_admin_supabase()
    user_id = current["profile"]["id"]

    sub_json = json.dumps({
        "endpoint": payload.endpoint,
        "keys": {
            "p256dh": payload.keys.p256dh,
            "auth":   payload.keys.auth,
        },
    })

    # Upsert — same endpoint, update user_id
    sb.table("push_subscriptions").upsert(
        {
            "endpoint":          payload.endpoint,
            "user_id":           user_id,
            "subscription_json": sub_json,
        },
        on_conflict="endpoint",
    ).execute()

    logger.info("Push subscribed | user=%s endpoint=%s...", user_id, payload.endpoint[:40])
    return {"message": "Subscribed successfully"}


# ── DELETE unsubscribe ────────────────────────────────────────────────────────
@router.delete("/unsubscribe")
def unsubscribe(
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    sb.table("push_subscriptions").delete().eq("endpoint", payload.endpoint).execute()
    logger.info("Push unsubscribed | user=%s", current["profile"]["id"])
    return {"message": "Unsubscribed successfully"}