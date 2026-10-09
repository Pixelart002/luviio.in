# Operations, CI and Release Flow

Last reviewed: 2026-09-16

## CI pipeline

The current GitHub Actions workflow runs on pushes and pull requests targeting `main`.

```text
Checkout
  -> Python 3.13
  -> install uv
  -> uv lock
  -> uv sync --dev
  -> compileall app
  -> Ruff
  -> Mypy
  -> pip-audit --strict
  -> pytest -q + coverage artifact
```

The dependency contract is `pyproject.toml` + `uv.lock`.

## Local verification

```bash
uv lock --check
uv sync --locked --dev
uv run python -m compileall -q app
uv run ruff check app tests
uv run mypy app --config-file mypy.ini
uv run pip-audit --strict
uv run pytest -q
```

For a production dependency-only verification:

```bash
uv sync --locked --no-dev --no-editable
```

## Deployment runtime

The runtime entrypoint is `app.main:app`. Production configuration is supplied through environment variables. Server-only secrets never belong in the frontend bundle or repository.

## Health model

```text
/health/live
  -> process/config identity only

/health
  -> database connectivity check with bounded retries
  -> 503 if DB cannot be reached

/api/v1/health/live
/api/v1/health
  -> same health handlers through versioned mount
```

## Smoke test after deployment

```text
1. GET /
2. GET /health/live
3. GET /health
4. GET /api/v1/products
5. GET /api/v1/categories
6. login/session flow
7. /api/v1/cart
8. create/update cart item
9. shipping-rate calculation
10. coupon application where configured
11. COD checkout
12. Stripe test checkout + webhook
13. customer order lookup by order_number
14. invoice PDF download
15. review submit/moderation
16. admin verify + dashboard
17. settings read/update where authorized
18. RBAC catalogue/effective matrix
19. share-card HTML/OG response
```

## Release gate

A domain is production-ready only when all of the following are true:

```text
implementation
+ authorization
+ failure handling
+ idempotency/concurrency
+ database integrity
+ automated tests
+ CI green
+ production configuration verified
+ observability
+ documentation
= release-ready domain
```

## Rollback

Rollback must restore the last known-good application commit and compatible dependency lock. Database migrations must be backward-safe or accompanied by an explicit rollback/recovery procedure. Never roll back application code while assuming an incompatible schema will remain safe.

## Observability

Every request should be traceable using sanitized request/correlation IDs. Errors should reach Sentry when configured. Operational actions should be visible through structured audit/logging without secrets.

## Performance review targets

Known areas requiring measurement before optimization include:

- `/api/v1/users/me`
- `/api/v1/cart`
- `/api/v1/cart/items`
- checkout/order creation
- `/api/v1/payments/create-intent`
- product creation with media

Measure p50/p95/p99, database round trips, payload size, N+1 queries and provider wait time before changing architecture or indexes.

## Shared HTTP token-bucket rate limiter

The global API rate-limit gate is implemented in `app/core/rate_limit.py` and backed by PostgreSQL via the `consume_http_token_bucket` RPC. The migration is `migrations/20260927095000_shared_http_token_bucket_rate_limit.sql`.

### Runtime behavior

- Applies to HTTP requests whose path starts with `/api/v1`; `OPTIONS` requests bypass the limiter.
- The key is a SHA-256 hash of the client IP. The real client IP is accepted from forwarding headers only when the immediate peer matches configured `TRUSTED_PROXY_IPS`; otherwise the peer IP is used.
- Bucket capacity is `RATE_LIMIT_PER_MINUTE` and refill duration is 60 seconds. Each allowed request consumes one token; tokens refill continuously up to capacity.
- State is shared across Koyeb workers in `private.http_token_bucket_state`; it is not a process-local counter.
- The application RPC timeout is 2 seconds. If the RPC is unavailable, malformed, or times out, the middleware fails closed with HTTP 503 and `error=rate_limiter_unavailable`. A valid bucket denial returns HTTP 429 with `error=rate_limit_exceeded` and a `Retry-After` header.
- The database cleanup function removes bucket rows not updated for 24 hours. Verify how/when cleanup is scheduled in the deployed database; do not assume the function runs automatically merely because it exists.

### Verify the database migration

Run in the Supabase SQL Editor with an operator account:

```sql
select to_regclass('private.http_token_bucket_state') as bucket_table;

select
  n.nspname as schema_name,
  p.proname as function_name,
  pg_get_function_identity_arguments(p.oid) as arguments
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'private'
  and p.proname in (
    'consume_http_token_bucket',
    'cleanup_http_token_bucket_state'
  )
order by p.proname;
```

Expected: the private state table and both private functions exist. The application calls the RPC name `consume_http_token_bucket`; confirm the Supabase RPC schema/exposure configuration resolves it to the private function in the current deployment. Do not grant `anon` or `authenticated` direct access to the private table or function.

### Inspect bucket state safely

Use a privileged SQL Editor session. Do not expose raw `rate_key` values in shared screenshots or logs: they are hashes derived from client IPs and can still act as correlatable identifiers.

```sql
select
  count(*) as active_bucket_rows,
  min(updated_at) as oldest_updated_at,
  max(updated_at) as newest_updated_at
from private.http_token_bucket_state
where updated_at >= now() - interval '24 hours';
```

For recent operational activity without disclosing individual keys:

```sql
select
  date_trunc('minute', updated_at) as minute,
  count(*) as bucket_rows_updated
from private.http_token_bucket_state
where updated_at >= now() - interval '60 minutes'
group by 1
order by 1 desc;
```

The table stores current token count and refill timestamps, not a complete request log. It cannot by itself prove which request was denied. Avoid manually changing or deleting rows during normal diagnosis.

### Verify production behavior

1. Check Koyeb logs for `Shared token-bucket unavailable`. This indicates the limiter RPC path failed or exceeded the 2-second timeout; it is not a normal rate-limit denial.
2. A normal denial is HTTP 429 with `rate_limit_exceeded` and `Retry-After`. A limiter infrastructure failure is HTTP 503 with `rate_limiter_unavailable`.
3. Confirm `RATE_LIMIT_PER_MINUTE`, `TRUSTED_PROXY_IPS`, Supabase connectivity, service-role client initialization and migration state before changing capacity.
4. If testing, use a staging environment or a controlled low-volume test from one client IP. Do not run aggressive loops against production; the bucket is shared across workers and requests from the same IP consume the same bucket.
5. Do not add a process-local fallback without an explicit security/availability decision: it would no longer provide one consistent global limit across workers.

### Troubleshooting

| Symptom | Interpretation | First checks |
|---|---|---|
| HTTP 429 / `rate_limit_exceeded` | Bucket denied a request because fewer than one token was available | Check configured capacity, request burst, `Retry-After`, and whether many clients share one public IP |
| HTTP 503 / `rate_limiter_unavailable` | The limiter could not safely determine whether to allow the request | Check Koyeb error type, Supabase RPC latency/connectivity, database locks, and deployed function/schema configuration |
| Slow API requests near the limiter warning | The RPC wait or other downstream work may be contributing; correlation is not proof of sole cause | Compare request duration, RPC timeout warnings, database query latency and Supabase health |
| Many bucket rows | Many distinct client-IP hashes have been seen recently | Check cleanup execution and traffic patterns; do not expose raw keys |
| Unexpected shared-IP throttling | Several users may appear behind one NAT/proxy address | Verify trusted proxy configuration and actual peer IP; never trust arbitrary forwarded headers |


