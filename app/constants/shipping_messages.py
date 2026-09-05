"""
Shipping Messages & Rules (SSOT)
================================
Path: app/constants/shipping_messages.py
"""

class ShippingSecurityMessages:
    METHOD_NOT_FOUND = "Shipping method not found."
    NO_METHOD = "No shipping method is available for this destination / cart."
    INVALID_TYPE = "Shipping method type is invalid."

class ShippingMessages:
    METHODS_FETCHED = "Shipping methods fetched successfully."
    RATE_COMPUTED = "Shipping rate computed successfully."
    METHOD_CREATED = "Shipping method created successfully."
    METHOD_UPDATED = "Shipping method updated successfully."
    METHOD_DELETED = "Shipping method deleted successfully."

# Method types
SHIPPING_FLAT = "flat"
SHIPPING_FREE_THRESHOLD = "free_threshold"
SHIPPING_PER_ITEM = "per_item"
SHIPPING_WEIGHT = "weight"
