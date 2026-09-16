# Production Readiness — Luviio.in

Last reviewed: 2026-09-16

## Verified

- Authentication/session flow and authorization boundaries have focused regression coverage.
- Shipping calculation is centralized and has threshold/disabled/invalid-config tests.
- Checkout/payment race handling has coverage for duplicate confirmation, duplicate webhooks, cancellation races, refund failure, and concurrent settlement.
- Inventory cancellation/restoration is owned by the Inventory domain.
- Coupon lifecycle/redemption constraints are enforced in the database layer.
- Product-level GST and immutable invoice snapshot layers are present.
- Duplicate performance indexes identified by the Supabase advisor were removed after verifying identical definitions.
- Durable `event_outbox` storage exists with retry-oriented columns (`attempts`, `next_retry_at`, `locked_at`, `last_error`, `processed_at`).
- Current outbox/DLQ operational check was clean at review time: no pending/failed outbox records and no pending/failed notification-DLQ records.

## Remaining configuration/runtime work

### 1. Supabase Auth

Enable leaked-password protection in the Supabase Auth password-security settings. This is an Auth configuration item, not a public-schema migration.

### 2. Durable event delivery

The database outbox is present, but application event publication still uses the in-process EventBus. Before treating the outbox as the delivery source of truth, add a transactional enqueue path and an idempotent worker that claims, delivers, retries, and marks events processed. Do not add a second non-transactional publish path.

### 3. Endpoint latency

Run production-like timing against `/api/v1/users/me`, `/api/v1/cart`, `/api/v1/cart/items`, and payment intent creation. Optimize only after capturing query/request traces; do not remove unused indexes solely from advisor INFO findings.

### 4. Frontend production verification

Verify the current Vercel deployment after the pending build completes: root route, direct reloads, product page, cart, checkout, order page, share-card preview, and console/network errors.

### 5. SEO/AEO/GEO + legal

Complete final production verification for canonical metadata, structured data, robots/sitemap/LLM discovery files, privacy/terms/refund/shipping pages, and India-specific consumer/GST disclosures.

## Verification commands

```bash
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
uv run pytest -q
```

## Rule for cleanup

Do not delete a legacy module, index, compatibility path, or runtime component until a repository-wide reference scan proves it has no live dependency and the replacement has regression coverage.
