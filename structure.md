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
    │       ├── api.py
    │       └── routers/
    │           ├── health.py
    │           └── invoice.py
    ├── core/
    ├── constants/
    ├── cron/
    ├── enums/
    ├── events/
    ├── integrations/
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

`app/domains/<domain>/router.py` owns domain HTTP routing, `service.py` owns business rules/orchestration, and `repository.py` owns database access. Shared DTOs remain under `app/api/schemas`; cross-cutting authorization remains under `app/permissions`; provider adapters remain under `app/integrations`.

`app/api/v1/api.py` is the route composition point. It imports feature routers from `app/domains/*/router.py`. Only `health.py` and `invoice.py` remain under `app/api/v1/routers/` because they are not duplicate feature routers.

## Cleanup status

Completed:

- Removed the old feature-router copies from `app/api/v1/routers/` after their domain router replacements were active.
- Removed the broken `My-frontend-` gitlink/submodule entry that had no `.gitmodules` definition.
- Kept `pyproject.toml` + `uv.lock` as the dependency source of truth.
- Updated the route aggregator to use canonical domain routers.

In progress:

- Repository-wide import migration from `app.services.*` / `app.repositories.*` to canonical domain modules.
- Removal of compatibility wrappers and legacy implementations only after zero-reference scans.
- Tests and deployment smoke verification after structural cleanup.

## Safe deletion rule

A legacy module is deleted only when:

1. Its canonical domain replacement exists.
2. Production code no longer imports it.
3. Tests no longer import it.
4. Documentation/examples no longer require it.
5. A repository-wide reference scan returns zero live references.
6. The replacement has been syntax/test checked.

This prevents architectural cleanup from causing a production outage.

For an exact tracked-file list, use `git ls-files` rather than maintaining a second manually curated tree.
