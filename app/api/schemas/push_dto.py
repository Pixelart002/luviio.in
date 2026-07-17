"""
Push Notification Schemas (DTOs)
================================
Path: app/api/schemas/push_dto.py
"""
from pydantic import BaseModel
from typing import List, Dict, Any

# ── Requests ──────────────────────────────────────────────────────────────────

class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscription(BaseModel):
    endpoint: str
    keys: SubscriptionKeys

class BatchNotificationRequest(BaseModel):
    user_ids: List[str]
    title: str = "Luviio"
    body: str
    icon: str = "/icons/ri-notification-3-line.png"
    url: str = "/"

# ── Responses ─────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str

class VapidKeyResponse(BaseModel):
    public_key: str

class SubscriptionStatusResponse(BaseModel):
    subscribed: bool
    subscription_count: int
    max_allowed: int
    vapid_configured: bool

class BatchNotificationResponse(BaseModel):
    success: int
    failed: int
    details: List[Dict[str, Any]]

class PushStatsResponse(BaseModel):
    total_subscriptions: int
    unique_users: int
    avg_per_user: float
    vapid_configured: bool