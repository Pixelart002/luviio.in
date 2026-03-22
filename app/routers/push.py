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


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


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
    user_id = current["profile"]["id"]

    sub_json = json.dumps({
        "endpoint": payload.endpoint,
        "keys": {
            "p256dh": payload.keys.p256dh,
            "auth": payload.keys.auth,
        },
    })

    sb.table("push_subscriptions").upsert(
        {
            "endpoint": payload.endpoint,
            "user_id": user_id,
            "subscription_json": sub_json,
        },
        on_conflict="endpoint",
    ).execute()

    logger.info("Push subscribed | user=%s endpoint=%.40s…", user_id, payload.endpoint)
    return {"message": "Subscribed successfully"}


@router.delete("/unsubscribe")
def unsubscribe(
    payload: PushSubscription,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    sb = get_admin_supabase()
    sb.table("push_subscriptions").delete().eq("endpoint", payload.endpoint).execute()
    logger.info("Push unsubscribed | user=%s", current["profile"]["id"])
    return {"message": "Unsubscribed successfully"}