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
    │   ├── schemas/
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

`app/api/v1/api.py` is the versioned HTTP composition point only. Domain HTTP routing belongs to `app/domains/<domain>/router.py`. Shared request/response DTO contracts remain under `app/api/schemas`; HTTP middleware remains under `app/api/middlewares`.

`app/infrastructure/health/router.py` owns the load-balancer/database health endpoint because health is cross-cutting infrastructure, not a business domain. Invoice generation is part of the Orders domain and is exposed from `app/domains/orders/router.py`.

Each domain owns its router, service, repository, and domain-specific contracts/policy where applicable. Cross-cutting authorization remains under `app/permissions`; provider adapters remain under `app/integrations`.

## API migration status

Completed:

- Removed all feature-router copies from `app/api/v1/routers/`.
- Migrated invoice HTTP routing into `app/domains/orders/router.py`.
- Migrated health HTTP routing into `app/infrastructure/health/router.py`.
- Updated `app/api/v1/api.py` and `app/main.py` to use the new locations.
- Removed the now-obsolete `app/api/v1/routers/` tracked files.
- Updated README and architecture documentation in the same cleanup cycle.

The API layer is intentionally retained as a thin transport/composition layer. `app/api/schemas` is not considered legacy merely because it lives under `api`; these are HTTP contract DTOs and are shared by domain routers.

## Broader cleanup status

In progress:

- Repository-wide import migration from `app.services.*` / `app.repositories.*` to canonical domain modules.
- Promotion of compatibility wrappers into concrete domain implementations where required.
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
