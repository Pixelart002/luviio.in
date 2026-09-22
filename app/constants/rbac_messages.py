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

# Human-readable admin notes: what each per-user control actually gates.
USER_ACTION_NOTES = {
    "checkout": "User ko checkout screen se order submit karne ki capability allow/block karta hai.",
    "place_order": "Final order create/place karne ki capability allow/block karta hai.",
    "apply_coupon": "Checkout/cart me coupon code apply karne ki capability allow/block karta hai.",
    "download_invoice": "User ko apne order ki invoice/PDF download karne ki capability allow/block karta hai.",
    "online_payment": "User ke liye online payment flow use karne ki capability allow/block karta hai.",
    "subscription_upgrade": "Subscription/tier upgrade karne ki capability allow/block karta hai.",
    "access_premium_products": "Premium-tier products ko access/purchase karne ki capability allow/block karta hai.",
    "access_platinum_products": "Platinum-tier products ko access/purchase karne ki capability allow/block karta hai.",
    "write_review": "Product review likhne/submit karne ki capability allow/block karta hai.",
}
