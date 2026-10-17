"""Push notification HTTP schemas owned by the Notifications domain."""
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _same_site_path(value: str | None, *, field_name: str) -> str | None:
    if value is None or value == "":
        return value
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise ValueError(f"{field_name} must be an in-site path beginning with '/'.")
    return value


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    p256dh: str = Field(..., min_length=1)
    auth: str = Field(..., min_length=1)


class PushSubscription(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    endpoint: str = Field(..., min_length=1)
    keys: SubscriptionKeys


class NotificationAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(..., min_length=1, max_length=30)
    action: str = Field(..., min_length=1, max_length=500)
    icon: str | None = Field(default=None, max_length=500)

    @field_validator("action")
    @classmethod
    def validate_action_path(cls, value: str) -> str:
        return _same_site_path(value, field_name="action") or "/"


class BatchNotificationRequest(BaseModel):
    """Validated, same-origin Web Push message and campaign options."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    user_ids: List[str] | None = Field(default=None, min_length=1, max_length=500)
    title: str = Field(default="Luviio", min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=2000)
    icon: str = Field(default="/icon-192.png", min_length=1, max_length=500)
    badge: str = Field(default="/icon-192.png", min_length=1, max_length=500)
    image: str | None = Field(default=None, max_length=500)
    url: str = Field(default="/", min_length=1, max_length=500)
    tag: str = Field(default="luviio-notification", min_length=1, max_length=100)
    require_interaction: bool = False
    renotify: bool = False
    actions: List[NotificationAction] = Field(default_factory=list, max_length=2)

    @field_validator("url", "icon", "badge", "image")
    @classmethod
    def validate_asset_paths(cls, value: str | None, info) -> str | None:
        return _same_site_path(value, field_name=info.field_name)
