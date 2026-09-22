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
  -> authentication and authorization dependencies
  -> domain service
  -> domain repository
  -> Supabase / external integration
```

## Architectural boundaries

- `app/main.py`: application assembly, lifespan, exception handling, middleware composition, and top-level health wiring.
- `app/api/v1/api.py`: versioned HTTP route composition only; no business logic.
- `app/api/middlewares`: stateless HTTP/ASGI transport concerns only.
- `app/domains/<domain>`: vertical feature slice containing router, service, repository, and domain-specific contracts/policy.
- `app/infrastructure`: cross-cutting infrastructure adapters/endpoints. Health monitoring lives under `app/infrastructure/health`.
- `app/permissions`: authorization policy decisions shared across domains.
- `app/core`: configuration, authentication dependencies, clients, shared middleware composition, logging, errors, and cross-cutting infrastructure.
- `app/integrations`: isolated third-party provider adapters.
- `app/events`: domain events and handlers.
- `app/cron`: idempotent scheduled work.
- `tests`: behavior and security regression coverage.
- `docs`: human-maintained system documentation.

## API ownership

Feature routing is owned by the corresponding domain. Invoice routing is owned by Orders; infrastructure health routing is owned by `app/infrastructure/health`.

Domain request/response contracts live with their owning bounded context. The versioned API layer composes routes but does not become a second business-model layer.

## Domain ownership

All feature implementations use canonical ownership under `app/domains/<domain>/`. The retired top-level `app/services` and `app/repositories` layers are not application boundaries and must not be reintroduced.

Payments have a single canonical repository at `app/domains/payments/repository.py`. Payment orchestration uses that repository and consumes pricing from `app/domains/pricing/service.py`. The canonical payment service is `app/domains/payments/service.py`.

Admin and Notifications likewise use their domain-owned router, service, and repository layers. External push, payment, email, and other provider calls remain behind `app/integrations` adapters.

## Authentication and authorization

Authentication establishes the server-verified subject. Authorization decisions are made by the permission/RBAC layer and enforced at the service boundary for privileged mutations and user-owned resources. Client-provided role or ownership fields are never trusted as authorization input.

## Persistence and correctness

Repositories own database access. Supabase is the persistence boundary; migrations are the schema source of truth. Correctness-critical operations such as checkout, payment settlement, inventory mutation, webhook idempotency, and ownership checks must rely on database constraints/transactions or other shared infrastructure rather than process-local state.

## Payments and webhooks

Payment integrations are isolated behind provider adapters. Webhook signatures are verified before business processing. Provider event IDs and payment identifiers are persisted for idempotency. Settlement uses database-backed integrity checks and transactions; replayed or concurrently delivered events must not double-settle an order.

## Observability

Every HTTP request receives sanitized `X-Request-ID` and `X-Correlation-ID` values. They are returned in responses and included in structured logs. Production logs are JSON; local logs are readable key/value lines. Secrets, cookies, authorization headers, payment data, and sensitive payloads are redacted. Sentry is opt-in through `SENTRY_DSN` and disabled in local/test environments.

## Middleware and horizontal scaling

Middleware is stateless and safe across multiple workers/instances. Request IDs are server-generated, body limits are enforced before business logic, security headers are centralized, and compression avoids already-compressed or streaming responses. Middleware state is never a correctness source of truth.

## Settings boundary

The Settings domain owns operational settings, validation, authorization, and persistence. Environment variables remain the source for secrets and deployment credentials. Settings are not a substitute for business records, RBAC policy, or provider credentials.

## Scaling rules

1. Keep routers thin and domain services focused.
2. Keep persistence behind repositories.
3. Never rely on process-local state for correctness across workers.
4. Preserve checkout/payment idempotency with database-backed guarantees.
5. Paginate unbounded collections and cap request/body sizes.
6. Isolate external providers behind integrations/adapters.
7. Make scheduled jobs idempotent and safe for multi-instance execution.
8. Keep production logging structured, bounded, and redacted.
9. Cover critical endpoints with success, validation, authorization, and failure-path tests.
10. Update this documentation whenever a production ownership boundary changes.

## Change and deletion policy

A structural change is complete only when the canonical replacement exists, production/tests/docs use it, the repository has no live references to the retired boundary, and CI is green.

Do not recreate compatibility shims or duplicate business-logic implementations. When a legacy module is removed, verify imports, tests, documentation, and deployment references before deletion.

## Verification standard

CI is the authoritative automated verification path. A production change is considered complete only after the relevant compile, lint, type-check, dependency-audit, and test gates pass.
