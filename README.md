# Luviio.in Backend

Luviio.in is a FastAPI backend organized for readable, secure, and predictable growth. The application entrypoint is `app.main:app`; versioned HTTP routes are mounted below `/api/v1`.

## Quick start

Requirements: Python 3.13 and `uv`.

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Useful checks:

```bash
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
uv run pytest -q
```

The test suite is recreated from scratch and documented in [`docs/TESTING.md`](docs/TESTING.md). It uses mocks at external service boundaries, so local tests do not require live Supabase, Stripe, email, push, or scheduler credentials.

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

- `app/api`: HTTP composition, versioning, shared DTO schemas, and API middleware.
- `app/api/v1/api.py`: the only versioned route composition point; it contains no business logic.
- `app/domains`: canonical feature ownership. Each migrated domain owns its router, service, repository, and domain-specific contracts/policy where applicable.
- `app/infrastructure`: cross-cutting infrastructure endpoints such as the load-balancer health router.
- `app/core`: authentication dependencies, configuration, middleware, Supabase clients, errors, logging, and shared infrastructure.
- `app/permissions`: authorization policies and permission definitions.
- `app/integrations`: Stripe, email, push, and other provider adapters.
- `app/events`: domain events and event handlers.
- `app/cron`: retry-safe scheduled jobs.
- `tests`: regression and security tests.
- `docs`: detailed design and operational guides.

Feature routers and invoice routing have been migrated out of `app/api/v1/routers/`. The legacy router directory is no longer part of the tracked source tree. Invoice generation now belongs to the Orders domain; health is an infrastructure concern under `app/infrastructure/health/`.

The Settings domain now owns its core engine and role-scoped settings services. Legacy `app/services/settings/*` implementations are cleanup candidates and will be removed only after the final repository-wide reference scan.

For the complete source tree and migration rules, read [`structure.md`](structure.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Environment variables

Copy the required names from `.env.example` when available. Secrets belong in the deployment environment, never in source control. `SB_SERVICE_ROLE_KEY` is server-only and must never be exposed in a response or browser bundle.

At minimum, configure the Supabase URL/key pair and the authentication/session values required by `app/core/config.py`. Provider-specific variables are only needed when that integration is enabled.

## Settings

System settings are operational configuration, not a secrets store. Admin routes are available under `/api/v1/settings/` and require the configured permission checks.

Typical settings include:

- `maintenance_mode`
- `enable_cod`
- `enable_online_payment`
- `tax_percentage`
- `shipping_charge`
- `minimum_order_value`
- `max_cart_items`

To add a setting: define its schema/database row, validate its type in the settings policy, read it from the relevant service, add tests, and document it in `docs/SETTINGS.md`. A setting does nothing until a feature explicitly reads it.

## Security rules

- Keep secrets in environment variables only.
- Use the server/admin Supabase client only on the server.
- Never trust user-editable metadata for authorization.
- Validate input at the DTO boundary and enforce authorization before business logic.
- Use explicit database columns and scoped queries.
- Do not log tokens, passwords, full payment data, or unnecessary personal data.
- Keep maintenance mode fail-safe and leave health/auth/settings recovery paths available.

See [`docs/SECURITY.md`](docs/SECURITY.md).

## Adding a feature

1. Add the request/response DTO.
2. Add the permission rule.
3. Add a focused service method.
4. Add repository queries with explicit columns.
5. Add success, invalid-input, unauthorized, and database-failure tests.
6. Update the relevant documentation.

Avoid putting business logic in routers or database queries in services. Do not delete a module until its replacement exists, imports are migrated, tests pass, and the change is recorded.

## Cleanup and replacements

| Old/stale item | Current replacement | Status |
|---|---|---|
| Feature routers in `app/api/v1/routers/` | `app/domains/*/router.py` | Removed |
| Invoice router in `app/api/v1/routers/invoice.py` | `app/domains/orders/router.py` | Migrated |
| Health router in `app/api/v1/routers/health.py` | `app/infrastructure/health/router.py` | Migrated |
| Settings core engine in `app/services/settings/core_engine.py` | `app/domains/settings/core_engine.py` | Promoted; legacy cleanup pending final scan |
| Settings role services in `app/services/settings/*_service.py` | `app/domains/settings/*_service.py` | Promoted; legacy cleanup pending final scan |
| `requirements.txt` | `pyproject.toml` + `uv.lock` | Removed |
| `test_backend_smoke_flow.py` | Focused tests under `tests/` | Removed/replaced |
| Duplicate settings storage logic | `SettingsCoreEngine` | Consolidated |
| Legacy services/repositories | Canonical domain services/repositories | Migrate imports first; delete only after zero-reference scan |

Compatibility code is removed only after the canonical replacement exists, all imports are migrated, and a repository-wide reference scan shows no live dependency. This prevents cleanup from becoming a production outage.

## Deployment

Vercel/Koyeb deployment configuration uses the Python package metadata and locked dependencies. Keep exactly one Python package-manager lockfile, run the locked sync check before deployment, and configure secrets through project environment variables.

More guides: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md), [`docs/API.md`](docs/API.md), and [`docs/DATABASE.md`](docs/DATABASE.md).

## License and ownership

Internal Luviio.in project. Changes should be small, reviewable, tested, and documented.
