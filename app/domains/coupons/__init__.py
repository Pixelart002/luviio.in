"""
Coupons Domain — promo/discount codes
=====================================
Path: app/domains/coupons/__init__.py

Full discount-coupon lifecycle: admin CRUD, customer validation & application,
usage/redemption tracking. Discount is computed over the order SUBTOTAL and
subtracted BEFORE tax is applied — product prices themselves are never
rewritten (see pricing separation in `app/domains/subscriptions`).

Tables: `coupons`, `coupon_redemptions`.
"""
__all__: list[str] = []
