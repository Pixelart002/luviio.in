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
