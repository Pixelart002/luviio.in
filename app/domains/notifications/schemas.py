"""
Push Notification Schemas (DTOs)
================================
Path: app/api/schemas/push_dto.py
"""
from pydantic import BaseModel, ConfigDict
from typing import List

class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    p256dh: str
    auth: str

class PushSubscription(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    endpoint: str
    keys: SubscriptionKeys

class BatchNotificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    user_ids: List[str]
    title: str = "Luviio"
    body: str
    icon: str = "/icons/ri-notification-3-line.png"
    url: str = "/"