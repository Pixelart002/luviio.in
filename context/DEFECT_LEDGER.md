# Backend Defect Ledger

## P0 / integrity

### D-001 — Direct client mutation of server-owned tables
**Status:** fixed in production DB.
**Root cause:** broad `anon` / `authenticated` table grants allowed browser writes subject only to row ownership RLS.
**Impact:** role/profile fields, order financial state, addresses, and cart price snapshots could be manipulated outside FastAPI business rules.
**Fix:** revoke all client table privileges for `users`, `addresses`, `carts`, `cart_items`, and `orders`. Backend APIs are now the mutation boundary.
**Verification:** live `information_schema.role_table_grants` returns no rows for those tables and client roles.

### D-002 — Cart price snapshot was only application-trusted
**Status:** fixed at access boundary.
**Root cause:** `cart_items.price_snapshot` was writable through direct Supabase table access.
**Fix:** direct table mutation removed; `CartService.add_item()` creates the snapshot from the authoritative product price.

## P1 / security and reliability

### D-003 — Worker-local auth brute-force state
**Status:** fixed.
**Fix:** shared Postgres throttle table + service-role RPCs; AuthPolicy is async and fail-closed on throttle infrastructure failure.

### D-004 — Transactional outbox functions client-executable
**Status:** fixed in production DB.
**Fix:** revoke public/client execution; service_role only.

### D-005 — Abandoned-cart push API mismatch
**Status:** fixed in code.
**Fix:** current async `send_push_to_user()` contract is awaited directly.

### D-006 — Six unindexed foreign keys
**Status:** fixed in production DB.
**Fix:** indexes added for addresses.user_id, audit_logs.actor_user_id, notification_dlq.user_id, payment_ledger.payment_id, product_reviews.user_id, and user_subscriptions.plan_id.

### D-007 — Stale RBAC/profile cache
**Status:** fixed in code.
**Fix:** profile cache TTL reduced to 60 seconds and explicit invalidation added after administrative user mutations. Sensitive authorization remains server-side.

### D-008 — Process-local global rate limit / proxy IP ambiguity
**Status:** fixed for the global API ceiling.
**Fix:** explicit trusted proxy IP/CIDR handling plus service-role-only Postgres-backed global rate-limit state. Endpoint-specific SlowAPI limits remain intentionally separate and process-local.

### D-009 — Stripe intent may exist without a persisted pending order
**Status:** mitigated with durable compensation + reconciliation.
**Fix:** durable checkout attempts, provider cancellation compensation, orphan-risk state, and scheduled reconciliation/refund handling are implemented.

### D-010 — CI static/type gate
**Status:** fixed and currently green.
**Verification:** latest payment-test PR #69 passed compile, Ruff, Mypy, dependency audit, and pytest+coverage before merge.

### D-017 — Admin could self-escalate through role permission overrides
**Status:** fixed and CI-verified.
**Fix:** role-target management policy prevents admins from editing the admin/super_admin roles; DELETE uses the same policy.

### D-018 — Inventory permissions were missing from the role matrix
**Status:** fixed and CI-verified.
**Fix:** canonical inventory permissions are granted by role and exposed through the RBAC catalogue with targeted role-matrix coverage.

### D-019 — Dynamic RBAC override loader failed open
**Status:** fixed and CI-verified.
**Fix:** normal roles receive an empty effective permission set when the override source is unavailable; super_admin wildcard behavior remains unchanged.

### D-020 — Per-user action-control loader failed open
**Status:** fixed and CI-verified.
**Fix:** action-control reads fail closed when policy state is unavailable.

### D-021 — User action-control deletion could self-unlock an admin
**Status:** fixed and CI-verified.
**Fix:** delete applies the strict actor-ID/self-lockout policy before removing an override.

### D-022 — Abandoned-cart permissions missing from role matrix
**Status:** fixed and CI-verified.
**Fix:** canonical abandoned-cart permissions are granted to admin/manager and exposed in the RBAC catalogue with targeted tests.

### D-023 — Low-stock scan used a read permission for a mutating action
**Status:** fixed and CI-verified.
**Fix:** dedicated `inventory.low_stock.scan` permission is required for the mutating scan endpoint; support retains read-only access.

## P2 / operations

### D-011 — Auth leaked-password protection disabled
**Status:** production configuration item — still open.
**Verification:** Supabase security advisor currently reports this warning. It must be enabled in the Supabase Auth configuration UI; the available database connector cannot change this Auth setting.

### D-012 — Business asset storage orphaning
**Status:** functionally fixed in code.
**Residual:** if Storage deletion itself fails, the setting reference remains correct and a warning is logged. Periodic garbage collection can remove unreachable objects later.

### D-013 — Settings mutations are chatty
**Status:** fixed and targeted-test verified.
**Fix:** identical updates and no-op resets short-circuit without unnecessary persistence/cache/event work.

### D-014 — Push circuit breaker / limiter is process-local
**Status:** fixed with shared Postgres state and live DB verification.
**Fix:** shared delivery state, atomic guard/success/failure RPCs, and fail-closed behavior.

### D-015 — Dependency/framework deprecation warnings
**Status:** partially addressed; controlled modernization remains open.
**Fixed:** removed direct `gotrue.AsyncMemoryStorage` import.
**Remaining:** older Supabase client line and dependency-level Starlette/httpx, Pydantic field-extra, and deprecated HTTP-status warnings require a separately verified lockfile upgrade.

### D-016 — Test coverage depth
**Status:** substantially expanded; operationally open for continuous depth validation.
**Added/verified:** rate-limit identity-boundary tests, RBAC role boundaries, inventory permissions, payment race coverage, and checkout action-control isolation. Latest CI completed successfully.
**Remaining:** maintain targeted security/concurrency coverage and verify critical-domain coverage thresholds from the CI artifact rather than treating generic test count as completeness.

## Production verification gates (not application defects)

- Stripe test payment + webhook end-to-end smoke.
- COD checkout smoke.
- Coupon reserve/apply/redeem smoke.
- Invoice PDF generation and statutory field verification.
- Notification provider delivery smoke.
- Current p50/p95/p99 performance baseline for documented hot paths.
- Final seller GST/legal configuration verification.

## Index advisory policy

Supabase currently reports ten indexes as unused. This is not sufficient evidence for deletion. The six FK indexes added during hardening and newer operational indexes must not be removed solely from the advisory; representative workload/query-plan evidence is required first.
