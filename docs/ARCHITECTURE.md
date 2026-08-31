# Luviio Backend Architecture

## Purpose

Luviio is a FastAPI backend. The application entrypoint is `app.main:app`; API routes are mounted by `app.api.v1.api:api_router` under `/api/v1`.

## Request flow

```text
Client
  -> FastAPI application (`app/main.py`)
  -> security, CORS, rate-limit and request logging middleware
  -> maintenance guard (`app/core/maintenance.py`)
  -> versioned router (`app/api/v1/routers`)
  -> Pydantic DTO (`app/api/schemas`)
  -> permission/auth dependency (`app/core/dependencies.py`, `app/permissions`)
  -> service (`app/services`)
  -> repository (`app/repositories`)
  -> Supabase (`app/core/supabase.py`)
```

## Folder rules

- `app/api/v1/routers`: HTTP-only concerns. Parse input, call a service, return the established response envelope.
- `app/api/schemas`: request and response DTOs. Never put database queries here.
- `app/services`: business rules and orchestration. Services must not know about HTTP request objects.
- `app/repositories`: database access only. Use explicit selected columns and parameterized Supabase filters.
- `app/permissions`: role and policy decisions. Do not use user-editable metadata for authorization.
- `app/core`: configuration, clients, middleware, errors, logging and cross-cutting infrastructure.
- `app/integrations`: external provider wrappers such as Stripe, email and push providers.
- `app/events`: domain event names and handlers.
- `app/cron`: scheduled jobs; jobs must be idempotent and safe to retry.
- `tests`: behavior and security regression tests.
- `docs`: human-maintained operational and design documentation.

## Rules for adding a feature

1. Add or update a DTO in `app/api/schemas`.
2. Add authorization before business logic.
3. Put business rules in a focused service.
4. Put Supabase access in a repository.
5. Keep the existing API response shape unless a compatibility alias is added.
6. Add success, invalid-input, unauthorized and database-failure tests.
7. Update the relevant document in `docs/`.

## Configuration and secrets

Runtime configuration is loaded by `app/core/config.py`. Secrets are environment variables only. Never commit `.env` files, service-role keys, JWT secrets, webhook secrets or provider credentials. `SB_SERVICE_ROLE_KEY` is server-only and must never be returned to a client.

## Maintenance mode

`app/core/maintenance.py` reads the `maintenance_mode` setting and blocks business routes with HTTP 503. Health, authentication, settings and documentation routes remain available so operators can recover the system. A database read failure fails open to avoid an accidental global outage; the settings API and logs remain the source for diagnosing that failure.

## Dependency policy

`pyproject.toml` and `uv.lock` are the only dependency sources. Run `uv lock --check` and `uv sync --locked` before deployment. Do not reintroduce `requirements.txt` or a second package manager.

## Safe cleanup policy

A module is removed only after a replacement exists, all imports are migrated, tests pass, and the removal is recorded in the change report. Generated `__pycache__` files are not source and must not be committed.

## Verification checklist

```text
uv lock --check
uv sync --locked --no-dev --no-editable
python -m compileall -q app
pytest
```

The exact current source tree can be regenerated with `git ls-files` from the repository root; this avoids maintaining a second, silently stale copy of the tree.
