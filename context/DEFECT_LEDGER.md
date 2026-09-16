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
**Verification:** targeted tests now cover untrusted spoofing, trusted Cloudflare IPs, invalid forwarded values, CIDR configuration, invalid proxy configuration, and forwarded-chain parsing.
**Remaining:** SlowAPI storage is still process-local. For true cross-worker/global throttling, move the limiter store to shared Redis/edge/DB-backed storage.

### D-009 — Stripe intent may exist without a persisted pending order
**Status:** mitigated with durable compensation + reconciliation.
**Fixed:** a service-role-only durable checkout attempt is created before provider creation and tracks provider/order lifecycle. Provider creation failures close the attempt. Atomic order-persistence failures trigger provider cancellation; cancellation failures become `orphan_risk`.
**Reconciliation:** a 15-minute sweep checks expired durable attempts; cancelled/nonexistent provider objects are closed, cancellable provider objects are cancelled, and succeeded provider objects without a Luviio order are refunded and marked completed when refund succeeds.

### D-010 — CI static/type gate
**Status:** fixed and verified on current main.
**Fix:** restored the complete invoice renderer and declared the module-level `ST` style registry type. Fresh CI runs on commits `0e3913c7` and `9c674a80` passed.

## P2 / operations

### D-011 — Auth leaked-password protection disabled
**Status:** deferred for test credentials; production go-live configuration item.

### D-012 — Business asset storage orphaning
**Status:** fixed in code.
**Root cause:** every business logo/signature upload created a new immutable object; a later settings write could fail, or a successful replacement could leave the previous object indefinitely.
**Fix:** the API now captures the previous asset reference, deletes the newly uploaded object if the settings mutation fails, and deletes the superseded managed object after the new setting is committed. Resetting a business asset setting also removes the managed object. Cleanup is restricted to canonical HTTPS URLs in the `business-assets` bucket; external URLs are never deleted.
**Residual:** if Storage deletion itself fails, the reference remains correct and a warning is logged; a future scheduled garbage-collection sweep can remove such unreachable objects.

### D-013 — Settings mutations are chatty
**Status:** fixed in code.
**Root cause:** repeated writes of an already-current setting still performed a database UPDATE, cache invalidation, and SettingUpdatedEvent dispatch.
**Fix:** settings mutations now short-circuit identical values; resets also short-circuit when the setting already equals its default. Real changes retain the existing persistence, cache invalidation, and event behavior.
**Verification:** targeted async tests cover identical update, real update, and no-op reset semantics.

### D-014 — Push circuit breaker / limiter is process-local
**Status:** fixed with shared Postgres state.
**Root cause:** circuit and per-endpoint rate state lived in Python process memory, so separate Koyeb workers could independently exceed the intended limits and circuit state disappeared on restart.
**Fix:** added service-role-only `private.push_delivery_state` plus atomic `push_delivery_guard`, `push_delivery_record_success`, and `push_delivery_record_failure` RPCs. Push delivery now uses the shared guard and fails closed if the guard storage is unavailable. The policy remains 3 attempts per endpoint per second, trips after 5 consecutive terminal failures, and resets after 60 seconds or a successful delivery.
**Verification:** live production SQL verified the table and function privileges (`anon`/`authenticated` denied; `service_role` allowed). A live database assertion verified the 3-per-window rate gate, 5-failure circuit trip, and fresh-state recovery. Targeted unit tests cover the service-role RPC boundary and fail-closed behavior.

### D-015 — Dependency/framework deprecation warnings
**Status:** partially addressed; full dependency modernization remains open.
**Fixed:** removed Luviio's direct `gotrue.AsyncMemoryStorage` import. Supabase client creation now uses its default in-memory auth storage, preserving the existing stateless-session behavior without a direct dependency on the deprecated package name.
**Remaining:** the project still pins the older Supabase client line, and dependency-level Starlette/httpx, Pydantic field-extra, and deprecated HTTP-status warnings require a separately verified upgrade because dependency resolution must remain green.

### D-016 — Test coverage depth
**Status:** partially addressed; broader targeted coverage remains open.
**Added:** rate-limit identity-boundary tests for proxy trust, spoofing resistance, CIDR configuration, invalid headers, and forwarded chains.
**Required next:** retain/add targeted security/concurrency tests for authorization boundaries, coupon reservation, payment races, and document snapshot immutability; do not mark this complete until the full CI coverage artifact confirms the intended critical-domain depth.
