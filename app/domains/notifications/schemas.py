"""Push notification HTTP schemas owned by the Notifications domain."""
from typing import List
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings


def _same_site_path(value: str | None, *, field_name: str) -> str | None:
    if value is None or value == "":
        return value
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        raise ValueError(f"{field_name} must be an in-site path beginning with '/'.")
    return value


def _notification_asset_reference(value: str | None, *, field_name: str) -> str | None:
    """Accept a site path or a Luviio notification image in the configured public bucket."""
    if value is None or value == "":
        return value

    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value

    try:
        parsed = urlsplit(value)
        storage_origin = urlsplit(settings.SB_URL)
        path_parts = parsed.path.split("/")
        is_luviio_notification_asset = (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.hostname == storage_origin.hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.startswith("/storage/v1/object/public/product-images/notifications/")
            and parsed.path.endswith(".webp")
            and ".." not in path_parts
            and "\\" not in parsed.path
        )
    except (TypeError, ValueError):
        is_luviio_notification_asset = False

    if is_luviio_notification_asset:
        return value
    raise ValueError(f"{field_name} must be an in-site path or a Luviio-hosted notification image.")


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

    @field_validator("action", "icon")
    @classmethod
    def validate_action_path(cls, value: str | None, info) -> str | None:
        return _same_site_path(value, field_name=info.field_name)


class BatchNotificationRequest(BaseModel):
    """Validated, same-origin Web Push message and campaign options."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    user_ids: List[str] | None = Field(default=None, min_length=1, max_length=500)
    title: str = Field(default="Luviio", min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=2000)
    icon: str = Field(default="/icon-512.png", min_length=1, max_length=500)
    badge: str = Field(default="/icon-512.png", min_length=1, max_length=500)
    image: str | None = Field(default=None, max_length=500)
    url: str = Field(default="/", min_length=1, max_length=500)
    tag: str | None = Field(default=None, max_length=100)
    require_interaction: bool = False
    renotify: bool = False
    actions: List[NotificationAction] = Field(default_factory=list, max_length=2)

    @field_validator("url", "icon", "badge", "image")
    @classmethod
    def validate_asset_paths(cls, value: str | None, info) -> str | None:
        if info.field_name == "url":
            return _same_site_path(value, field_name=info.field_name)
        return _notification_asset_reference(value, field_name=info.field_name)

    @model_validator(mode="after")
    def require_tag_for_renotify(self):
        if self.renotify and not (self.tag and self.tag.strip()):
            raise ValueError("A campaign tag is required when re-alerting a replaced notification.")
        return self
