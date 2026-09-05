"""
Coupon Permissions Registry
===========================
Path: app/permissions/coupons.py
"""
class CouponPermissions:
    CREATE = "coupons.create"
    READ = "coupons.read"
    UPDATE = "coupons.update"
    DELETE = "coupons.delete"
    APPLY = "coupons.apply"  # customer-side — granted to all logged-in users (ABAC) in practice
