# Backend State — 2026-09-16

## Audit baseline
Repository: `Pixelart002/luviio.in`
Database: Supabase production project `enqcujmzxtrbfkaungpm`

## Completed in this hardening pass
- Removed direct `anon` / `authenticated` table privileges for `users`, `addresses`, `carts`, `cart_items`, and `orders`.
- Restricted transactional event-outbox trigger functions to `service_role`.
- Added six missing foreign-key indexes reported by Supabase advisors.
- Added shared database-backed authentication throttle state and service-role RPCs.
- Switched auth policy/service calls to asynchronous shared throttling.
- Fixed abandoned-cart push delivery to use the current async `send_push_to_user()` contract.

## Existing protections verified before this pass
- Payment settlement RPCs are generally service-role-only.
- Coupon reserve/redeem functions are service-role-only.
- Inventory mutation RPCs are service-role-only.
- Sensitive payment/invoice/outbox tables have RLS and deny-client policies.
- Coupon reservation is part of pending-order creation transaction.
- Customer order numbers are unique.

## Remaining tracked items
1. CI currently has Ruff I001/E702 failures; source formatting must be cleaned and CI rerun through the test stage.
2. Supabase Auth leaked-password protection must be enabled in the Supabase Auth configuration UI; this cannot be changed by the available database connector.
3. Profile/RBAC cache invalidation should be tied to admin role/is_active mutation or replaced with a short-lived authoritative lookup for sensitive permissions.
4. Global HTTP rate limiting should use a shared store and trusted proxy/IP handling rather than process-local buckets.
5. PaymentIntent creation vs pending-order persistence still needs orphan-intent recovery/idempotent compensation.
6. Business asset replacement should garbage-collect superseded storage objects.

## Verification policy
Never mark an item fixed because code exists. Mark it fixed only after one of:
- live database verification,
- CI execution,
- targeted automated test,
- deployment/runtime log verification.
