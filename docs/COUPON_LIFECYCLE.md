# Coupon Lifecycle

Last reviewed: 2026-09-16

## Authority

Coupon validity and discount calculation are backend-authoritative. The frontend only collects the code and displays the server response.

## Checkout lifecycle

```text
Customer enters coupon
        |
        v
CouponService validation
        |
        +--> active / validity window / minimum order
        +--> global usage limit
        +--> per-user limit
        |
        v
Server calculates discount
        |
        v
create_pending_order_with_reservation()
        |
        +--> create order
        +--> reserve inventory
        +--> reserve coupon capacity atomically
        |
        +--> any failure = whole transaction rolls back
        |
        v
PENDING order
        |
        +--> payment succeeds
        |       -> record_coupon_redemption()
        |       -> reservation becomes REDEEMED
        |       -> used_count increments once
        |
        +--> order cancelled / abandoned
                -> release_coupon_reservation(order_id)
                -> inventory reservation released
                -> coupon capacity becomes available again
```

## Single-use invariant

For `per_user_limit = 1`, a user cannot create multiple simultaneous orders consuming the same coupon. The reservation is created during the order transaction rather than waiting for payment settlement.

## Concurrency

The reservation function locks the coupon row with `FOR UPDATE`, checks active reservations/redemptions, and inserts the reservation before the order transaction returns. A unique `(coupon_id, user_id, order_id)` constraint makes the same order idempotent.

## Expiry

Pending online reservations expire after their configured reservation window. A scheduled maintenance job removes expired reservation rows every five minutes. The reservation query also ignores expired rows, so stale rows cannot consume capacity.

## Cancellation

Order cancellation calls `release_coupon_reservation(order_id)`. Only `reserved` rows are released; redeemed coupon usage is never rolled back by ordinary cancellation.

## Administration

The admin console shows:

- total usage: `used_count / usage_limit`
- per-user limit
- active/inactive state
- validity window
- discount type/value/cap

Coupon codes are normalized to trimmed uppercase in the backend regardless of frontend input casing.

## Operational checks

```text
Single-use coupon -> first checkout reserves -> second checkout blocked
Same order retry   -> existing reservation remains idempotent
Payment success    -> reserved -> redeemed exactly once
Cancellation       -> reserved row released
Expired reservation-> cleanup job removes stale row
Global limit       -> reserved + redeemed capacity enforced
```
