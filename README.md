# Luviio.in Backend

Luviio.in is a FastAPI backend organized for readable, secure, and predictable growth. The application entrypoint is `app.main:app`; versioned HTTP routes are mounted below `/api/v1`.

## Quick start

Requirements: Python 3.13 and `uv`.

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Containerized startup:

```bash
cp .env.example .env
# Fill required deployment values in .env
docker compose up --build
```

Production logs are structured JSON; local development logs are readable key/value lines. Every response includes sanitized `X-Request-ID` and `X-Correlation-ID` headers for tracing a request across services. Configure `SENTRY_DSN` only in non-local deployments when error tracking is desired.

## Verification

```bash
uv lock --check
uv sync --locked --dev
uv run python -m compileall -q app
uv run ruff check app tests
uv run mypy app --config-file mypy.ini
uv run pip-audit --strict
uv run pytest -q
```

`pyproject.toml` and `uv.lock` are the only dependency files. Do not add `requirements.txt`, Pipenv, Poetry, or another lockfile.

## Architecture

```text
Request
  -> app/main.py
  -> middleware / maintenance guard
  -> app/api/v1/api.py
  -> app/domains/<domain>/router.py
  -> app/domains/<domain>/service.py
  -> app/domains/<domain>/repository.py
  -> Supabase / integrations
```

- `app/api`: HTTP composition, versioning and transport concerns.
- `app/domains`: canonical feature ownership.
- `app/infrastructure`: health/share infrastructure.
- `app/core`: configuration, auth dependencies, middleware, errors, logging and clients.
- `app/permissions`: authorization capability definitions.
- `app/integrations`: third-party adapters.
- `app/events`: domain events/handlers.
- `app/cron`: scheduled jobs.
- `tests`: regression/security coverage.
- `docs`: system and operator documentation.

## Complete documentation map

Start here: [`docs/README.md`](docs/README.md)

| Guide | Covers |
|---|---|
| [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) | Complete architecture and domain ownership |
| [`docs/DEPENDENCY_GRAPH.md`](docs/DEPENDENCY_GRAPH.md) | Python dependencies + domain dependency graph |
| [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) | Complete endpoint inventory and access model |
| [`docs/USER_FLOWS.md`](docs/USER_FLOWS.md) | Customer/user workflows end-to-end |
| [`docs/ADMIN_FLOWS.md`](docs/ADMIN_FLOWS.md) | Admin/operator workflows and permissions |
| [`docs/DATA_SECURITY.md`](docs/DATA_SECURITY.md) | Auth, RBAC/ABAC, ownership, data boundaries |
| [`docs/BACKGROUND_WORKFLOWS.md`](docs/BACKGROUND_WORKFLOWS.md) | Events, cron, outbox, notification and retry workflows |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | CI, health, deploy, smoke test and rollback |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Detailed architecture rules |
| [`docs/API.md`](docs/API.md) | API conventions/compatibility rules |
| [`docs/DATABASE.md`](docs/DATABASE.md) | Database boundaries and persistence rules |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Security controls |
| [`docs/SETTINGS.md`](docs/SETTINGS.md) | System-settings contract |
| [`docs/TESTING.md`](docs/TESTING.md) | Test strategy and CI standard |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | Deployment/release rules |
| [`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md) | Verified items and remaining runtime/config work |

## API size

The current source defines **105 distinct route handlers** across its router modules. The root application adds one process-root handler, making **106 distinct application handlers**. Because the health router is mounted both at root and under `/api/v1`, the application has **108 concrete URL registrations**. See [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md) for the complete method/path inventory.

## Security rules

- Keep secrets in environment variables only.
- Use the server/admin Supabase client only on the server.
- Never trust user-editable metadata for authorization.
- Validate input at the DTO boundary and enforce authorization before business logic.
- Use explicit database columns and scoped queries.
- Do not log tokens, passwords, full payment data, or unnecessary personal data.
- Keep maintenance mode fail-safe and leave health/auth/settings recovery paths available.

## Feature-change rule

1. Add or update the request/response DTO.
2. Add/update the permission rule.
3. Add the focused service use-case.
4. Add repository/persistence changes with explicit projections.
5. Add success, invalid-input, unauthorized, concurrency and failure-path tests as applicable.
6. Update the matching documentation in the same change.

A structural change is complete only when the canonical replacement exists, imports are migrated, tests pass, production configuration is correct, and documentation reflects the actual implementation.
