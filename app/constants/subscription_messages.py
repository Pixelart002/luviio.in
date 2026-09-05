"""
Subscription Messages & Tier Rules (SSOT)
=========================================
Path: app/constants/subscription_messages.py
"""

# The three membership tiers. `free` is the default for every new customer.
# Top tier is `platinum` (enterprise-grade, most perks).
TIERS = {
    "free": {"label": "Free", "sort": 0},
    "premium": {"label": "Premium", "sort": 1},
    "platinum": {"label": "Platinum", "sort": 2},
}

class SubscriptionSecurityMessages:
    PLAN_NOT_FOUND = "Subscription plan not found."
    TIER_INVALID = "Invalid membership tier."
    USER_NOT_FOUND = "User not found."
    OFFER_UNAVAILABLE = "This plan is not available / not active."
    ACTION_BLOCKED = "This action has been disabled for your account by the policy team."

class SubscriptionMessages:
    PLAN_CREATED = "Subscription plan created successfully."
    PLAN_UPDATED = "Subscription plan updated successfully."
    PLAN_DELETED = "Subscription plan deleted successfully."
    PLANS_FETCHED = "Subscription plans fetched successfully."
    SUBSCRIBED = "Membership activated successfully."
    CHANGED = "Membership tier changed successfully."
    MINE_FETCHED = "Your membership fetched successfully."
    USERS_UPDATED = "User memberships updated successfully."
    TIER_SEPARATION = (
        "Tier perks are separate from product pricing. "
        "Product price lives in products.pricing; tier perks live in the tier registry."
    )
