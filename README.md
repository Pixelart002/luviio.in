# Luviio.in — Full-Stack Commerce Application

Luviio is maintained as a single repository containing the FastAPI backend and Vite/React frontend. The repository is the source of truth for application code, contracts, workflows and operational documentation.

## Repository layout

```text
luviio.in/
├── app/                    # FastAPI backend
├── frontend/               # React + Vite browser application
├── migrations/             # reviewed database migrations
├── tests/                  # backend regression/security tests
├── docs/                   # canonical system/workflow/operation docs
├── pyproject.toml
├── uv.lock
└── vercel.json
```

## Runtime architecture

```text
Browser
  -> Vercel frontend
  -> /api/v1
  -> FastAPI middleware
  -> domain router
  -> domain service/policy
  -> repository / transaction / RPC
  -> Supabase/Postgres
  -> provider adapters
```

The frontend is a browser client. Server-side pricing, GST/tax, shipping, inventory, authorization, order state and payment state remain authoritative in backend/domain/database boundaries.

## Frontend

Current frontend stack: React + TypeScript + Vite + React Router. Browser API access is centralized in `frontend/src/api/`.

Current public/customer routes:

- `/`
- `/shop`
- `/product/:slug`
- `/cart`
- `/checkout`
- `/orders`
- `/account`
- `/register`

The current browser route map and known UI/backend gaps are tracked in [`docs/FRONTEND_SYSTEM_MAP.md`](docs/FRONTEND_SYSTEM_MAP.md).

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

Frontend:

```bash
cd frontend
npm ci
npm run build
npm run lint
```

## Canonical documentation

Start here: [`docs/README.md`](docs/README.md)

| Guide | Covers |
|---|---|
| [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) | Backend/runtime architecture and domain ownership |
| [`docs/FRONTEND_SYSTEM_MAP.md`](docs/FRONTEND_SYSTEM_MAP.md) | Frontend routes, browser architecture and API boundary |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | HTTP endpoint inventory and access model |
| [`docs/USER_FLOWS.md`](docs/USER_FLOWS.md) | Customer backend lifecycle |
| [`docs/ADMIN_FLOWS.md`](docs/ADMIN_FLOWS.md) | Admin/operator backend lifecycle |
| [`docs/BROWSER_WORKFLOWS.md`](docs/BROWSER_WORKFLOWS.md) | Production browser acceptance workflows |
| [`docs/BACKGROUND_WORKFLOWS.md`](docs/BACKGROUND_WORKFLOWS.md) | Events, cron, outbox and retry workflows |
| [`docs/FULFILLMENT_WORKFLOW.md`](docs/FULFILLMENT_WORKFLOW.md) | Shipping/fulfillment lifecycle |
| [`docs/DATA_SECURITY.md`](docs/DATA_SECURITY.md) | Auth, RBAC/ABAC, ownership and data boundaries |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | CI, health, deployment, smoke and rollback |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy and CI gates |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment/release rules |
| [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) | Verified state and remaining operational gates |

## Documentation rule

A feature change is complete only when its code, API/security contract, browser behavior, failure states, tests and matching documentation agree.

The browser workflow document is the bridge between a user action and the backend outcome that must be proven.