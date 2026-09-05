"""
RBAC / User-Action-Control Messages (SSOT)
==========================================
Path: app/constants/rbac_messages.py
"""

class RbacMessages:
    OVERRIDES_FETCHED = "Role permission toggles fetched successfully."
    OVERRIDE_UPDATED = "Role permission override saved successfully."
    OVERRIDE_DELETED = "Role permission override removed (falling back to default)."
    CATALOGUE = "Permission catalogue fetched successfully."

    USER_CONTROLS_FETCHED = "User action controls fetched successfully."
    USER_CONTROL_UPDATED = "User action control updated successfully."
    USER_CONTROL_DELETED = "User action control removed (default enabled)."

# Canonical list of user actions an admin can enable/disable per user.
USER_ACTIONS = [
    "checkout",
    "place_order",
    "apply_coupon",
    "download_invoice",
    "online_payment",
    "subscription_upgrade",
    "access_premium_products",
    "access_platinum_products",
    "write_review",
]
