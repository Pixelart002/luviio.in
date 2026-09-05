# Luviio.in Backend Architecture

## System design

```text
HTTP request
  -> FastAPI app (`app/main.py`)
  -> stateless HTTP middleware: security, CORS, request logging, body limits, compression
  -> maintenance guard
  -> versioned composition (`app/api/v1/api.py`)
  -> domain router (`app/domains/<domain>/router.py`)
  -> domain-owned Pydantic schema (`app/domains/<domain>/schemas.py`)
  -> auth and permission dependencies
  -> domain service
  -> domain repository
  -> Supabase / integrations
```

## Folder responsibilities

- `app/api/v1/api.py`: thin versioned route composition only; no business logic.
- `app/api/middlewares`: stateless HTTP/ASGI transport concerns only.
- `app/domains/<domain>`: vertical feature slice containing router, business service, repository, and domain-specific contracts/policy.
- `app/infrastructure`: cross-cutting infrastructure adapters/endpoints. Health monitoring lives under `app/infrastructure/health`.
- `app/services` and `app/repositories`: legacy compatibility area being migrated; new feature code must use canonical domain modules.
- `app/permissions`: authorization policy decisions.
- `app/core`: configuration, authentication dependencies, clients, shared middleware composition, logging, and errors.
- `app/integrations`: isolated third-party adapters.
- `app/events`: domain events and handlers.
- `app/cron`: idempotent scheduled work.
- `tests`: behavior and security regression coverage.
- `docs`: human-maintained system documentation.

## API transport migration

The old feature-router copies under `app/api/v1/routers/` have been removed. Invoice routing is owned by Orders, while health routing is owned by infrastructure.

The old shared `app/api/schemas` DTO package has now been retired. Domain request/response contracts live with their owning bounded context, preventing the API layer from becoming a second business-model layer.

The API layer is intentionally thin: `app/main.py` owns application assembly, `app/api/v1/api.py` composes the versioned route table, and domain/infrastructure modules own endpoint behavior.

## Payment domain migration

Payments now have a single canonical repository under `app/domains/payments/repository.py`. The abandoned-order cron imports that repository directly, and payment tests target `app/domains/payments/service.py` ownership. The duplicate legacy payment service under `app/services/payments/service.py` has been removed.

`app/repositories/payment_repo.py` is retained only as a temporary compatibility shim for legacy consumers; it re-exports the canonical payments repository and contains no independent persistence implementation. It must be removed after the remaining legacy repository imports are migrated and verification is complete.

## Middleware and horizontal scaling

Middleware remains outside domains because it applies uniformly to every worker/instance. Request IDs are server-generated, body limits are enforced before oversized payloads reach business logic, security headers are added centrally, and compression avoids already-compressed/streaming responses. Middleware must remain stateless and must never be a correctness source of truth; shared correctness state belongs in database/cache infrastructure.

## Settings boundary

The Settings domain owns `SettingsCoreEngine`, role-scoped settings services, and its repository. New feature code must not depend on the legacy settings service package.

## Scaling rules

1. Keep routers thin and domain services focused.
2. Keep persistence behind repositories.
3. Never rely on process-local state for correctness across multiple workers.
4. Preserve checkout/payment idempotency; use database-backed constraints/transactions for correctness.
5. Paginate unbounded collections and cap payload sizes.
6. Isolate external providers behind integrations/adapters.
7. Make scheduled jobs idempotent so multiple workers cannot corrupt state.
8. Avoid unbounded per-request logging; production logging should be structured and operationally controllable.
9. Add positive, invalid-input, unauthorized, and failure-path tests for critical endpoints.
10. Update architecture docs whenever ownership or boundaries change.

## Safe migration rule

Never remove a legacy module because its name looks old. First add the canonical replacement, migrate every import, run syntax/tests, perform a repository-wide reference scan, then remove the stale module. Temporary compatibility shims are acceptable only when they contain no duplicate business logic and have an explicit removal condition.