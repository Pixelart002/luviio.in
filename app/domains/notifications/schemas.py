"""
Notifications Domain Schemas (DTOs)
===================================
Path: app/domains/notifications/schemas.py
"""
from app.api.schemas.push_dto import (
    SubscriptionKeys,
    PushSubscription,
    BatchNotificationRequest,
)

__all__ = [
    "SubscriptionKeys",
    "PushSubscription",
    "BatchNotificationRequest",
]
