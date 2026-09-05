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
    │       ├── __init__.py
    │       └── router.py
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

`app/api/v1/api.py` is the versioned HTTP composition point only. Domain HTTP routing belongs to `app/domains/<domain>/router.py`. Domain-specific HTTP schemas now live with their owning domain under `app/domains/<domain>/schemas.py`. `app/api/schemas` is being retired after all imports are migrated.

`app/api/middlewares` remains the correct boundary for HTTP/ASGI middleware. These components are cross-cutting transport concerns, not business-domain logic.

`app/infrastructure/health/router.py` owns the load-balancer/database health endpoint because health is cross-cutting infrastructure, not a business domain. Invoice generation is part of the Orders domain and is exposed from `app/domains/orders/router.py`.

Each domain owns its router, service, repository, and domain-specific contracts/policy where applicable. Cross-cutting authorization remains under `app/permissions`; provider adapters remain under `app/integrations`.

## API/schema migration status

Completed:

- Removed all feature-router copies from `app/api/v1/routers/`.
- Migrated invoice HTTP routing into `app/domains/orders/router.py`.
- Migrated health HTTP routing into `app/infrastructure/health/router.py`.
- Migrated Auth, Cart, Orders, Payments, Settings, and Users routers to domain-owned schemas.
- Confirmed domain-owned schema modules exist for the migrated vertical slices.
- Kept middleware under the HTTP transport boundary and hardened request-ID/header behavior.
- Updated documentation alongside the structural changes.

Remaining schema migration:

- Products and Notifications router imports still need migration to their domain schema modules.
- Admin schema ownership is already under `app/domains/admin/schemas.py`; remaining consumers should use that path.
- After all imports are migrated, perform a repository-wide zero-reference scan and delete `app/api/schemas/` only if no live references remain.

## Middleware boundary

`app/api/middlewares` currently owns CORS, request logging, request IDs, body-size limits, GZip, server-header hardening, and browser security headers. `app/core/setup_middlewares.py` is the composition point and should remain free of business logic.

Security middleware now generates a server-owned UUID request ID, strips client-supplied duplicate IDs, removes framework fingerprint headers instead of advertising a custom server signature, and emits HSTS only for HTTPS requests.

## Broader cleanup status

In progress:

- Final repository-wide reference scan for legacy `app/services/settings/*` implementations before deletion.
- Repository-wide import migration from remaining `app.services.*` / `app.repositories.*` to canonical domain modules.
- Completion of remaining API schema imports and deletion of the old API schema package after verification.
- Removal of legacy implementations only after zero-reference scans.
- Syntax/tests and deployment smoke verification after structural cleanup.

## Safe deletion rule

A legacy module is deleted only when:

1. Its canonical replacement exists.
2. Production code no longer imports it.
3. Tests no longer import it.
4. Documentation/examples no longer require it.
5. A repository-wide reference scan returns zero live references.
6. The replacement has been syntax/test checked.

This prevents architectural cleanup from causing a production outage.

For an exact tracked-file list, use `git ls-files` rather than maintaining a second manually curated tree.
