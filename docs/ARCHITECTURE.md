# Luviio.in Backend Architecture

## System design

```text
HTTP request
  -> FastAPI app (`app/main.py`)
  -> middleware: security, CORS, rate limits, request logging
  -> maintenance guard
  -> versioned composition (`app/api/v1/api.py`)
  -> domain router (`app/domains/<domain>/router.py`)
  -> Pydantic DTO (`app/api/schemas`)
  -> auth and permission dependencies
  -> domain service
  -> domain repository
  -> Supabase / integrations
```

## Folder responsibilities

- `app/api/v1/api.py`: thin versioned route composition only; no business logic.
- `app/api/schemas`: typed HTTP input/output contracts shared by domain routers.
- `app/api/middlewares`: HTTP middleware concerns.
- `app/domains/<domain>`: vertical feature slice containing router, business service, repository, and domain-specific contracts/policy where applicable.
- `app/infrastructure`: cross-cutting infrastructure adapters/endpoints. Health monitoring lives under `app/infrastructure/health`.
- `app/services` and `app/repositories`: legacy compatibility area being migrated; new feature code must use canonical domain modules.
- `app/permissions`: authorization policy decisions.
- `app/core`: configuration, authentication dependencies, clients, shared middleware, logging, and errors.
- `app/integrations`: isolated third-party adapters.
- `app/events`: domain events and handlers.
- `app/cron`: idempotent scheduled work.
- `tests`: behavior and security regression coverage.
- `docs`: human-maintained system documentation.

## API transport migration

The old feature-router copies under `app/api/v1/routers/` have been removed. Invoice routing was moved into `app/domains/orders/router.py`, where it belongs to the Orders bounded context. Health routing was moved into `app/infrastructure/health/router.py`, where it is treated as cross-cutting infrastructure.

The API layer is therefore intentionally thin: `app/main.py` owns application assembly, `app/api/v1/api.py` composes the versioned route table, and domain/infrastructure modules own endpoint behavior.

## Settings boundary

`SettingsCoreEngine` is the single storage/cache/event pipeline. `AdminSettingsService`, `ManagerSettingsService`, and `CustomerSettingsService` are role-specific policy facades. The old `SettingsService` import remains as a compatibility facade and delegates to the same engine; new code must prefer the role-specific services.

## Change rules

1. Add the request/response contract at the appropriate API/domain boundary.
2. Authorize before business logic.
3. Put business rules in a focused domain service.
4. Put all database access in a repository.
5. Preserve response contracts unless adding a compatibility alias.
6. Add positive, invalid-input, unauthorized, and database-failure tests.
7. Update the source-tree and architecture documentation when structural ownership changes.

Never remove a module because its name looks old. First add the replacement, migrate every import, run syntax/tests, scan references, then remove the stale module.
