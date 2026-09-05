"""
Coupon Messages & Rules (SSOT)
==============================
Path: app/constants/coupon_messages.py
"""

class CouponSecurityMessages:
    NOT_FOUND = "Coupon not found."
    INVALID = "This coupon code is not valid."
    EXPIRED = "This coupon has expired."
    NOT_STARTED = "This coupon is not active yet."
    MIN_ORDER_NOT_MET = "This coupon requires a minimum order value to apply."
    USAGE_LIMIT_REACHED = "This coupon has reached its usage limit."
    USER_LIMIT_REACHED = "You have already used this coupon the maximum number of times."
    INACTIVE = "This coupon is currently not active."
    STACKING_NOT_ALLOWED = "Only one coupon can be applied per order."

class CouponMessages:
    CREATED = "Coupon created successfully."
    UPDATED = "Coupon updated successfully."
    DELETED = "Coupon deleted successfully."
    FETCHED = "Coupons fetched successfully."
    APPLIED = "Coupon applied successfully."

# Supported value types
COUPON_TYPE_PERCENT = "percent"
COUPON_TYPE_FIXED = "fixed"
