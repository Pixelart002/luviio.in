"""
Push Notification Schemas — Strict Pydantic DTOs
================================================
Path: app/api/schemas/push_dto.py
"""
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from typing import List, Dict, Any

# ── Requests ──

class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    p256dh: str = Field(..., description="Elliptic curve Diffie-Hellman public key")
    auth: str = Field(..., description="Authentication secret")

class PushSubscription(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    endpoint: HttpUrl = Field(..., description="Secure HTTPS WebPush endpoint URL")
    keys: SubscriptionKeys

class BatchNotificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    user_ids: List[str] = Field(..., description="List of target user UUIDs")
    title: str = Field(default="Luviio", max_length=100)
    body: str = Field(..., max_length=500)
    icon: str = Field(default="/icons/ri-notification-3-line.png")
    url: str = Field(default="/")

# ── Responses ──

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