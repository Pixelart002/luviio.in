# Luviio Backend — Verified Source Tree

Git is the authority for tracked filenames. Generated `__pycache__/` files are excluded.

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

`app/api/v1/api.py` is the versioned HTTP composition point only. Domain HTTP routing belongs to `app/domains/<domain>/router.py`; infrastructure health belongs to `app/infrastructure/health/router.py`.

`app/api/middlewares` is the HTTP/ASGI transport boundary for cross-cutting concerns. It must not contain business-domain logic.

Each domain owns its router, service, repository, and domain-specific contracts/policy where applicable. Cross-cutting authorization remains under `app/permissions`; external-provider adapters remain under `app/integrations`.

## Canonical architecture

The legacy top-level `app/services/*` and `app/repositories/*` feature layers are retired. New application code must use canonical domain modules and must not import those legacy paths.

Payment ownership is `app/domains/payments/`; pricing ownership is `app/domains/pricing/`.

## Middleware boundary

`app/api/middlewares` owns CORS, request logging, request IDs, body-size limits, GZip, server-header hardening, and browser security headers. Middleware is stateless/per-request so it can run safely across horizontally scaled workers.

## Scaling principles

- Keep routers thin: validation, authentication/authorization, orchestration, response mapping.
- Keep business logic in domain services; persistence behind repositories.
- Avoid process-local state as a source of truth; shared correctness state belongs in database/cache infrastructure.
- Preserve idempotency for checkout/payment operations and avoid in-memory locks for correctness.
- Paginate unbounded collection endpoints and cap request/body sizes.
- Use provider integrations behind adapters so external services can be replaced or scaled independently.
- Keep scheduled jobs idempotent so multiple workers cannot corrupt state.
- Treat CI as the required verification gate for production changes.

## Safe deletion rule

A legacy module is deleted only when its canonical replacement exists, production and tests no longer import it, documentation/examples no longer require it, a repository-wide reference scan returns zero live references, and the replacement passes verification.
