# Luviio Backend — Verified Source Tree

> Git is the authority for exact tracked filenames. Generated `__pycache__/` files are excluded.

```text
luviio.in/
├── .env.example
├── .gitignore
├── .python-version
├── Procfile
├── pyproject.toml
├── uv.lock
├── structure.md
├── docs/
├── migrations/
├── tests/
└── app/
    ├── main.py
    ├── api/
    │   ├── middlewares/
    │   └── v1/
    │       └── api.py
    ├── core/
    ├── constants/
    ├── cron/
    ├── enums/
    ├── events/
    ├── integrations/
    ├── infrastructure/
    │   └── health/
    ├── permissions/
    ├── utils/
    └── domains/
        ├── admin/
        ├── auth/
        ├── cart/
        ├── coupons/
        ├── inventory/
        ├── notifications/
        ├── orders/
        ├── payments/
        ├── pricing/
        ├── products/
        ├── rbac/
        ├── settings/
        ├── shipping/
        ├── subscriptions/
        └── users/
```

## Ownership

`app/api/v1/api.py` is the versioned HTTP composition point only. Domain HTTP routing belongs to `app/domains/<domain>/router.py`. Domain-specific HTTP schemas live with their owning domain under `app/domains/<domain>/schemas.py`. The shared `app/api/schemas` package is being retired after remaining imports are migrated.

`app/api/middlewares` remains the HTTP/ASGI transport boundary for cross-cutting concerns. It must not contain business-domain logic. `app/core/setup_middlewares.py` is the composition point.

`app/infrastructure/health/router.py` owns infrastructure health. Invoice generation is owned by Orders and exposed from `app/domains/orders/router.py`.

Each domain owns its router, service, repository, and domain-specific contracts/policy where applicable. Cross-cutting authorization remains under `app/permissions`; external-provider adapters remain under `app/integrations`.

## API/schema migration status

Completed:

- Removed all feature-router copies from `app/api/v1/routers/`.
- Migrated invoice HTTP routing into `app/domains/orders/router.py`.
- Migrated health HTTP routing into `app/infrastructure/health/router.py`.
- Migrated Auth, Cart, Orders, Payments, Settings, Users, Products, and Notifications routers to domain-owned schema modules.
- Removed migrated Products and Notifications DTO files from `app/api/schemas/`.
- Kept middleware at the HTTP boundary and hardened request-ID/header behavior.
- Updated documentation alongside structural changes.

Remaining:

- Migrate any remaining `app.api.schemas.*` imports.
- Perform a repository-wide zero-reference scan before removing the remaining shared schema files.
- Continue legacy `app.services.*` / `app.repositories.*` migration domain-by-domain.

## Middleware boundary

`app/api/middlewares` currently owns CORS, request logging, request IDs, body-size limits, GZip, server-header hardening, and browser security headers. Middleware is intentionally stateless/per-request so it can run safely across horizontally scaled workers.

Security middleware generates server-owned request IDs, strips client-supplied duplicate IDs, removes framework fingerprint headers, and emits HSTS only for HTTPS requests.

## Scaling principles

- Keep routers thin: validation, authentication/authorization, orchestration, response mapping.
- Keep business logic in domain services; persistence behind repositories.
- Avoid process-local state as a source of truth; shared state belongs in the database/cache infrastructure.
- Preserve idempotency for checkout/payment operations and avoid in-memory locks for correctness.
- Keep middleware stateless so multiple instances/workers behave consistently.
- Paginate unbounded collection endpoints and cap request/body sizes.
- Use provider integrations behind adapters so external services can be replaced or scaled independently.
- Delete legacy modules only after canonical replacement, reference scan, and verification.

## Safe deletion rule

A legacy module is deleted only when:

1. Its canonical replacement exists.
2. Production code no longer imports it.
3. Tests no longer import it.
4. Documentation/examples no longer require it.
5. A repository-wide reference scan returns zero live references.
6. The replacement is syntax/test checked.
