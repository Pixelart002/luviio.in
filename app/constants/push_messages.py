"""
Push Notification Messages & Security Strings (SSOT)
====================================================
Path: app/constants/push_messages.py
"""

class PushMessages:
    SUBSCRIBED = "Device securely subscribed to push notifications."
    UNSUBSCRIBED = "Device successfully unsubscribed from notifications."
    BATCH_SENT = "Batch notification dispatch completed."

class PushSecurityMessages:
    INVALID_ENDPOINT = "Security Violation: The provided push endpoint URL is invalid or unsupported."
    LIMIT_EXCEEDED = "Maximum allowed device subscriptions reached for this account."
    VAPID_NOT_CONFIGURED = "Push notifications are currently disabled on the server (Missing VAPID Configuration)."
    UNAUTHORIZED_BATCH = "You do not have permission to trigger bulk push notifications."
    SUBSCRIPTION_NOT_FOUND = "The requested device subscription could not be found."