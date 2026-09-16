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
**Root cause:** in-memory dictionaries differed across workers and reset on process restart.
**Fix:** shared Postgres throttle table + service-role RPCs; AuthPolicy is async and fail-closed on throttle infrastructure failure.

### D-004 — Transactional outbox functions client-executable
**Status:** fixed in production DB.
**Root cause:** three SECURITY DEFINER trigger functions retained EXECUTE for anon/authenticated.
**Fix:** revoke public/client execution; service_role only.

### D-005 — Abandoned-cart push API mismatch
**Status:** fixed in code.
**Root cause:** cart service called an older `send_push_to_user()` signature and did not await it.
**Fix:** call the current async contract directly.

### D-006 — Six unindexed foreign keys
**Status:** fixed in production DB.
**Fix:** indexes added for addresses.user_id, audit_logs.actor_user_id, notification_dlq.user_id, payment_ledger.payment_id, product_reviews.user_id, and user_subscriptions.plan_id.

### D-007 — Stale RBAC/profile cache
**Status:** fixed in code.
**Fix:** profile cache TTL reduced to 60 seconds and explicit invalidation added after administrative user mutations. Sensitive authorization still uses server-side profile state.

### D-008 — Process-local global rate limit / proxy IP ambiguity
**Status:** partially fixed; distributed storage remains open.
**Fixed:** forwarded client-IP headers are no longer trusted from arbitrary peers. `TRUSTED_PROXY_IPS` now explicitly defines trusted proxy IPs/CIDRs; invalid entries never grant trust, and the direct peer is the fallback identity.
**Remaining:** SlowAPI storage is still process-local. For true cross-worker/global throttling, move the limiter store to shared Redis/edge/DB-backed storage.

### D-009 — Stripe intent may exist without a persisted pending order
**Status:** partially mitigated; durable orphan reconciliation remains open.
**Fixed:** when the Stripe PaymentIntent is created but atomic order/reservation persistence fails, the service now attempts provider-side cancellation before returning the checkout error. If cancellation fails, a high-severity orphan-risk log is emitted.
**Remaining:** add a durable pre-provider checkout-attempt record and reconciliation sweep for provider intents that have no matching Luviio order.

### D-010 — CI static/type gate
**Status:** fixed and verified on current main.
**Fix:** restored the complete invoice renderer and declared the module-level `ST` style registry type. Fresh CI runs on commits `0e3913c7` and `9c674a80` passed.

## P2 / operations

### D-011 — Auth leaked-password protection disabled
**Status:** open; configuration action required in Supabase Auth settings.

### D-012 — Business asset storage orphaning
**Status:** open.
**Required fix:** keep previous asset reference and delete superseded object after new reference is committed.

### D-013 — Settings mutations are chatty
**Status:** open.
**Required fix:** batch validation/update/audit/cache invalidation where multiple settings change in one operation.

### D-014 — Push circuit breaker / limiter is process-local
**Status:** open.
**Required fix:** move distributed protection to shared storage or an external queue/provider boundary if multi-worker consistency is required.

### D-015 — Dependency/framework deprecation warnings
**Status:** open; warning-only cleanup.
**Scope:** gotrue, Starlette/httpx, Pydantic field-extra, and deprecated HTTP status constant usage observed in CI/runtime logs.

### D-016 — Test coverage depth
**Status:** open.
**Required fix:** add targeted security/concurrency tests for authorization boundaries, throttling, coupon reservation, payment races, and document snapshot immutability.
