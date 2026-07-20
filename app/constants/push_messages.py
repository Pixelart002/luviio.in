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
    NOT_CONFIGURED = "Push notifications are not configured on the server."
    INVALID_ENDPOINT = "Invalid push endpoint. Must be a secure HTTPS URL."
    DB_ERROR = "A database error occurred while managing the subscription."
    STATS_ERROR = "Failed to fetch push notification statistics."

class PushRules:
    MAX_SUBSCRIPTIONS_PER_USER = 5