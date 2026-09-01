# Luviio.in Backend Architecture

## System design

```text
HTTP request
  -> FastAPI app (`app/main.py`)
  -> middleware: security, CORS, rate limits, request logging
  -> maintenance guard
  -> versioned router (`app/api/v1/routers`)
  -> Pydantic DTO (`app/api/schemas`)
  -> auth and permission dependencies
  -> role-specific service
  -> repository
  -> Supabase
```

## Folder responsibilities

- `app/api/v1/routers`: HTTP concerns only.
- `app/api/schemas`: typed input/output contracts.
- `app/services`: business rules; no `Request` objects or raw database calls.
- `app/repositories`: Supabase access and explicit column selection.
- `app/permissions`: authorization policy decisions.
- `app/core`: configuration, clients, middleware, logging, and errors.
- `app/integrations`: isolated third-party adapters.
- `app/events`: domain events and handlers.
- `app/cron`: idempotent scheduled work.
- `tests`: behavior and security regression coverage.
- `docs`: human-maintained system documentation.

## Settings boundary

`SettingsCoreEngine` is the single storage/cache/event pipeline. `AdminSettingsService`, `ManagerSettingsService`, and `CustomerSettingsService` are role-specific policy facades. The old `SettingsService` import remains as a compatibility facade and delegates to the same engine; new code must prefer the role-specific services.

## Change rules

1. Add DTO first.
2. Authorize before business logic.
3. Put business rules in a focused service.
4. Put all database access in a repository.
5. Preserve response contracts unless adding a compatibility alias.
6. Add positive, invalid-input, unauthorized, and database-failure tests.
7. Update docs for operational behavior.

Never remove a module because its name looks old. First add the replacement, migrate every import, run checks, then record and remove the stale module in a separate change.
