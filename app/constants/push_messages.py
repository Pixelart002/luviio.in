"""
Push Notification Messages & Rules (SSOT)
=========================================
Path: app/constants/push_messages.py
"""

class PushMessages:
    SUBSCRIBED = "Subscribed to push notifications successfully."
    UNSUBSCRIBED = "Unsubscribed successfully."
    BATCH_SENT = "Batch notifications dispatched successfully."

class PushSecurityMessages:
    NOT_CONFIGURED = "Push notifications are not configured on the server (Missing VAPID keys)."
    INVALID_ENDPOINT = "Invalid push endpoint. Must be a secure HTTPS URL."
    BATCH_LIMIT_EXCEEDED = "Batch notification request exceeds the maximum allowed limit of {limit} users."
    DB_ERROR = "A database error occurred while managing the subscription ledger."
    STATS_ERROR = "Failed to fetch push notification telemetry statistics."
    DISPATCH_FAILED = "An error occurred while executing the notification broadcast."

class PushRules:
    MAX_SUBSCRIPTIONS_PER_USER = 5
    MAX_BATCH_SIZE = 500