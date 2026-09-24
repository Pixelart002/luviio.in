# Luviio.in — Backend API

Luviio's backend repository contains the production FastAPI API, domain services, persistence, integrations, background workflows and database migrations. The browser frontend is maintained separately.

## Repository layout

```text
luviio.in/
├── app/                    # FastAPI backend
├── migrations/             # reviewed database migrations
├── tests/                  # backend regression/security tests
├── docs/                   # backend/runtime/API/operations docs
├── pyproject.toml
└── uv.lock
```

## Runtime architecture

```text
Browser / external client
  -> HTTPS
  -> FastAPI middleware
  -> domain router
  -> domain service/policy
  -> repository / transaction / RPC
  -> Supabase/Postgres
  -> provider adapters
```

The backend is API-only. Pricing, GST/tax, shipping, inventory, authorization, order state, payment state and other business invariants remain authoritative inside backend/domain/database boundaries.

The separate frontend consumes the versioned `/api/v1` contract and is not built, served or deployed from this repository.

## Verification

Backend:

```bash
uv lock --check
uv sync --locked --dev
uv run python -m compileall -q app
uv run ruff check app tests
uv run mypy app --config-file mypy.ini
uv run pip-audit --strict
uv run pytest -q
```

## Canonical documentation

Start here: [`docs/README.md`](docs/README.md)

| Guide | Covers |
|---|---|
| [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) | Backend/runtime architecture and domain ownership |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | HTTP endpoint inventory and access model |
| [`docs/USER_FLOWS.md`](docs/USER_FLOWS.md) | Customer backend lifecycle |
| [`docs/ADMIN_FLOWS.md`](docs/ADMIN_FLOWS.md) | Admin/operator backend lifecycle |
| [`docs/BACKGROUND_WORKFLOWS.md`](docs/BACKGROUND_WORKFLOWS.md) | Events, cron, outbox and retry workflows |
| [`docs/FULFILLMENT_WORKFLOW.md`](docs/FULFILLMENT_WORKFLOW.md) | Shipping/fulfillment lifecycle |
| [`docs/DATA_SECURITY.md`](docs/DATA_SECURITY.md) | Auth, RBAC/ABAC, ownership and data boundaries |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | CI, health, deployment, smoke and rollback |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy and CI gates |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Backend deployment/release rules |
| [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) | Verified state and remaining operational gates |

## Documentation rule

A backend feature is complete only when its code, API/security contract, persistence/provider behavior, failure states, tests and matching backend documentation agree.
