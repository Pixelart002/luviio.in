# Production Readiness — Luviio.in

Last reviewed: 2026-09-17

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
- India-facing privacy policy now documents DPDP-oriented data categories, purposes, consent/withdrawal handling, privacy rights, retention, processor sharing, security/breach response, and the designated grievance contact.
- A dedicated `/privacy/dpdp` privacy notice is published by the frontend and provides a clear data-category/purpose notice plus rights-request and grievance routes.
- India-facing terms identify the Grievance Officer & Proprietor as Kyro and provide the official contact/address.
- Terms include current country-of-origin/product-disclosure handling where applicable and record readiness for the Consumer Protection (E-Commerce) (Amendment) Rules, 2026 effective 1 January 2027.

## Remaining configuration/runtime work

### 1. Supabase Auth

Enable leaked-password protection in the Supabase Auth password-security settings. This is an Auth configuration item, not a public-schema migration. This item is currently intentionally deferred.

### 2. Durable event delivery

The database outbox is present, but application event publication still uses the in-process EventBus. Before treating the outbox as the delivery source of truth, add a transactional enqueue path and an idempotent worker that claims, delivers, retries, and marks events processed. Do not add a second non-transactional publish path.

### 3. Endpoint latency

Run production-like timing against `/api/v1/users/me`, `/api/v1/cart`, `/api/v1/cart/items`, and payment intent creation. Optimize only after capturing query/request traces; do not remove unused indexes solely from advisor INFO findings.

### 4. Frontend production verification

Verify the current Vercel deployment after the pending build completes: root route, direct reloads, product page, cart, checkout, order page, policy routes including `/privacy/dpdp`, share-card preview, and console/network errors.

### 5. DPDP operational controls

The public notice and rights/grievance disclosure are now present. Before production go-live, verify the actual runtime controls for consent where required, withdrawal of consent, rights-request handling, retention/deletion execution, processor arrangements, and applicable personal-data-breach response/notification procedures. Do not claim a control is implemented merely because it is described in the policy.

### 6. India consumer/legal disclosures

Before production go-live, verify product-level country-of-origin and any applicable Legal Metrology declarations for pre-packaged goods, actual seller/legal identity and tax-registration details, and that pricing/discount disclosures match the live product data. Do not replace test GST credentials/configuration with invented production values.

### 7. Consumer Protection (E-Commerce) Amendment Rules, 2026

The 2026 amendments are scheduled to take effect on 1 January 2027. Before that date, verify applicable complaint-copy handling, National Consumer Helpline convergence, search-result transparency, sponsored-listing disclosure, prior/reduced price display, and related seller disclosures. Do not implement or represent future obligations as currently effective before their commencement date.

### 8. SEO/AEO/GEO

Complete final production verification for canonical metadata, structured data, robots/sitemap/LLM discovery files and indexability.

## Verification commands

```bash
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
uv run pytest -q
```

## Rule for cleanup

Do not delete a legacy module, index, compatibility path, or runtime component until a repository-wide reference scan proves it has no live dependency and the replacement has regression coverage.
