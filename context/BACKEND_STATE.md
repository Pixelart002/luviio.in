# Backend State — 2026-09-17

## Audit baseline
Repository: `Pixelart002/luviio.in`
Production database: Supabase project `enqcujmzxtrbfkaungpm`

## Current production-hardening state

The backend core commerce domains have completed the current hardening pass. The latest payment race test isolation was merged as PR #69 (`54a7b6cdac2c0ae5e8335f33c3b8156825a2d04c`) and its Backend CI was green before merge.

### Security / integrity protections verified
- Direct `anon` / `authenticated` table privileges removed from `users`, `addresses`, `carts`, `cart_items`, and `orders`.
- Transactional event-outbox trigger functions restricted to `service_role`.
- Payment settlement RPCs are service-role-only.
- Coupon reserve/redeem functions are service-role-only.
- Inventory mutation RPCs are service-role-only.
- Sensitive payment/invoice/outbox tables have RLS and deny-client policies.
- Coupon reservation is part of pending-order creation transaction.
- Customer order numbers are unique.
- Shared DB-backed authentication throttling is enabled.
- Global API rate-limit state is shared through Postgres; trusted-proxy handling is explicit and fail-safe.
- RBAC dynamic override reads fail closed.
- Per-user action-control reads fail closed.
- Admin role-management boundaries prevent self-escalation.
- Inventory, abandoned-cart, and low-stock permissions are represented in the canonical role matrix.
- PaymentIntent orphan-risk compensation/reconciliation is implemented.
- Push delivery limiter/circuit state is shared through Postgres.
- Business-asset replacement rollback/cleanup is implemented.
- Six FK indexes previously reported by Supabase advisors were added.

## Current CI state

Latest merged payment-test change passed the complete Backend CI pipeline:

`compile -> Ruff -> Mypy -> pip-audit -> pytest + coverage`

No known P0/P1 application defect is currently open in the defect ledger.

## Remaining external / operational gates

These are not unresolved core application defects:

1. **Supabase Auth leaked-password protection:** Supabase security advisor still reports this as disabled. It must be enabled in the Supabase Auth configuration UI; the available database connector cannot change this Auth setting.
2. **Live provider smoke:** Stripe test checkout/webhook, COD, coupon, notification provider, and invoice PDF should be exercised against the deployed environment as a release smoke suite.
3. **Statutory configuration:** seller GST/legal identity, state, GSTIN and invoice configuration must match the actual registered business before statutory invoicing.
4. **Performance baseline:** collect current p50/p95/p99 for the documented hot paths before further optimization.
5. **Dependency modernization:** older Supabase/httpx/Pydantic/HTTP-status dependency warnings remain a separate controlled upgrade task; do not upgrade blindly without lockfile + CI verification.
6. **Storage GC:** failed storage deletion can leave an unreachable object; the canonical setting reference remains correct. A periodic garbage-collection sweep is an operational enhancement.
7. **Documentation:** this file is now the authoritative current state; historical commit references in older documents should not be treated as current status.

## Index policy

Supabase currently reports ten indexes as unused. This is advisory information, not proof that they are safe to remove. The indexes include the six recently-added FK indexes and newer operational indexes. Do not delete them solely from the unused-index advisory; removal requires query-plan/usage evidence over a representative production workload.

## Verification policy

Never mark an item fixed because code merely exists. Mark it fixed only after one or more of:
- live database verification,
- CI execution,
- targeted automated test,
- deployment/runtime verification.

External configuration or provider tests must be labelled as such rather than represented as completed application code work.
