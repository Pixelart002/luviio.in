# Dependency Graph

Last reviewed: 2026-09-16

## 1. Runtime dependency layers

```text
Python 3.13
  |
  +-- FastAPI / Starlette / Uvicorn
  |      |
  |      +-- HTTP routing, middleware, lifecycle, OpenAPI
  |
  +-- Pydantic / pydantic-settings
  |      |
  |      +-- request DTO validation + typed configuration
  |
  +-- Supabase client
  |      |
  |      +-- PostgreSQL persistence / Auth / Storage
  |
  +-- Stripe + payment-plugin adapters
  |      |
  |      +-- payment intents / confirmation / webhooks
  |
  +-- Resend + WebPush
  |      |
  |      +-- email + push delivery
  |
  +-- ReportLab / Pillow
  |      |
  |      +-- invoice PDF + image handling
  |
  +-- slowapi / cachetools / APScheduler / Sentry
         |
         +-- rate limits / caches / scheduled jobs / observability
```

## 2. Direct Python dependencies

The production dependency contract is declared in `pyproject.toml` and locked by `uv.lock`.

| Package family | Current package(s) | Used for |
|---|---|---|
| API server | `fastapi`, `uvicorn[standard]` | HTTP API/runtime |
| Validation/config | `pydantic`, `pydantic-settings`, `email-validator` | schemas/config/email validation |
| Database/backend | `supabase` | Supabase/Postgres/Auth/Storage access |
| HTTP | `httpx`, `requests` | outbound HTTP boundaries |
| Payments | `stripe` | Stripe provider |
| Abuse controls | `slowapi` | endpoint rate limiting |
| Email | `resend` | email delivery |
| Push | `pywebpush` | Web Push delivery |
| Media/PDF | `Pillow`, `reportlab` | image and invoice processing |
| Observability | `sentry-sdk` | error reporting |
| Caching | `cachetools` | local cache layers |
| Scheduling | `apscheduler` | cron-style jobs |
| IDs | `nanoid` | compact public identifiers where used |

Development-only packages are separated in the `dev` dependency group: mypy, pip-audit, pytest, pytest-asyncio, pytest-cov and ruff.

## 3. Domain dependency graph

```text
                    +----------------+
                    |     Settings   |
                    +--------+-------+
                             |
               +-------------+-------------+
               v                           v
          +---------+                 +-----------+
          | Pricing |<--------------- | Shipping  |
          +----+----+                 +-----------+
               |
               v
Product --> Cart --> Coupon
  |           |         |
  |           +---------+
  |                 |
  +------------> Checkout <------------- Shipping
                    |
          +---------+----------+
          |                    |
          v                    v
      Inventory              Orders
          ^                    |
          |                    v
          +-------------- Payments
                             |
                             v
                     Payment ledger / attempts
                             |
                             v
                     Invoice snapshot/PDF

Reviews --> Orders (purchase eligibility)
Orders --> Notifications/events
Payments --> Notifications/events
Inventory --> Notifications/events
Users --> Auth/RBAC
Admin --> Users/Products/Orders/Payments/Settings/RBAC/Notifications
```

The arrows represent business dependency/use-case direction, not raw import counts.

## 4. Verified implementation edges

- Orders routes invoke `CheckoutService`, so checkout orchestration is owned by Checkout while the public HTTP surface remains in Orders.
- Payments directly depends on Inventory and Orders for payment cancellation, order ownership and stock restoration; payment provider access is isolated behind the plugin manager/context.
- Reviews verifies delivered purchases through the Orders data model before creating a review.
- Settings depends on authorization helpers and invalidates the maintenance cache after mutation/reset.
- Admin depends on the payment plugin manager for provider/method administration.
- Notifications depends on auth/user context and admin permissions for batch operations.
- RBAC is consumed through central permission dependencies and action-control enforcement.
- Social-share depends on ProductService rather than reading product tables directly.

## 5. Dependency direction rules

Allowed:

```text
router -> service -> repository/integration
service -> another domain service/use-case
repository -> database adapter
integration -> provider SDK
policy -> repository/service data needed for a decision
```

Avoid:

```text
router -> raw Supabase query
service -> HTTP Request/Response objects
one domain -> another domain's private repository to bypass invariants
provider SDK calls scattered across unrelated domains
```

## 6. Dependency upgrade policy

1. Change `pyproject.toml` deliberately.
2. Regenerate/verify `uv.lock` with `uv lock`.
3. Run compile, Ruff, mypy, pip-audit and pytest.
4. Review provider-specific breaking changes before enabling a major/minor upgrade in production.
5. Deploy only the lock-consistent package set.
6. Document any behavioral migration, not only the version number.

`requirements.txt`, Pipenv, Poetry lockfiles or a second package manager must not be introduced beside `pyproject.toml` + `uv.lock`.
