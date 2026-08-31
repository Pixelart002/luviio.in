# Luviio Backend — Verified Source Tree

> This document describes the current source layout. Git is the authority for exact tracked filenames; generated `__pycache__/` files are excluded.

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
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── SETTINGS.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── DEPLOYMENT.md
│   └── CONTRIBUTING.md
├── migrations/
└── app/
    ├── main.py
    ├── api/
    │   ├── middlewares/
    │   │   ├── cors.py
    │   │   ├── logger.py
    │   │   └── security.py
    │   ├── schemas/
    │   │   ├── admin_dto.py
    │   │   ├── auth_dto.py
    │   │   ├── cart_dto.py
    │   │   ├── order_dto.py
    │   │   ├── payment_dto.py
    │   │   ├── product_dto.py
    │   │   ├── push_dto.py
    │   │   ├── settings_dto.py
    │   │   └── user_dto.py
    │   └── v1/
    │       ├── api.py
    │       └── routers/
    │           ├── admin_verify.py
    │           ├── auth.py
    │           ├── cart.py
    │           ├── health.py
    │           ├── invoice.py
    │           ├── orders.py
    │           ├── payments.py
    │           ├── products.py
    │           ├── push.py
    │           ├── settings.py
    │           └── users.py
    ├── constants/
    ├── core/
    │   ├── config.py
    │   ├── dependencies.py
    │   ├── exceptions.py
    │   ├── logger.py
    │   ├── maintenance.py
    │   ├── monitoring.py
    │   ├── queue.py
    │   ├── rate_limit.py
    │   ├── setup_middlewares.py
    │   └── supabase.py
    ├── cron/
    ├── enums/
    ├── events/
    ├── permissions/
    ├── repositories/
    ├── services/
    │   ├── auth/
    │   ├── carts/
    │   ├── orders/
    │   ├── payments/
    │   ├── products/
    │   ├── push/
    │   ├── settings/
    │   └── users/
    └── utils/
└── tests/
```

## Ownership

`routers` handle HTTP, `schemas` validate data, `services` implement business rules, `repositories` talk to Supabase, `permissions` authorize, and `core` provides shared infrastructure. New features should follow that flow instead of adding database calls inside routers.

## Deprecated/stale entries removed from the old document

The old tree listed root `app.py`, `requirements.txt`, `app/api/v1/app.py`, `inventory.py`, and several folders that are not present in this repository. The real entrypoint is `app/main.py`; dependencies are managed only by `pyproject.toml` and `uv.lock`. No source module was deleted during this documentation pass without a verified replacement.

For an exact current list, use `git ls-files`; this prevents documentation from becoming a second stale source of truth.
