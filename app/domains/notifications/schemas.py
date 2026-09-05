"""Push notification HTTP schemas owned by the Notifications domain."""
from typing import List
from pydantic import BaseModel, ConfigDict, Field


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscription(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    endpoint: str = Field(..., min_length=1)
    keys: SubscriptionKeys


class BatchNotificationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    user_ids: List[str] = Field(..., min_length=1)
    title: str = Field(default="Luviio", min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=2000)
    icon: str = "/icons/ri-notification-3-line.png"
    url: str = "/"
