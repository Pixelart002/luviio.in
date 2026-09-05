"""
Subscription Permissions Registry
==================================
Path: app/permissions/subscriptions.py
"""
class SubscriptionPermissions:
    # Customer-facing
    READ_PLANS = "subscriptions.read_plans"
    SUBSCRIBE = "subscriptions.subscribe"
    READ_MINE = "subscriptions.read_mine"

    # Staff (admin) management
    MANAGE = "subscriptions.manage_features"  # edit plans/perks
    MANAGE_USERS = "subscriptions.manage_users"  # assign/revoke customer subscriptions
