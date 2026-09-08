# API Guide

## Base URL

The API origin is environment-specific. Do not hard-code a deployment hostname in application clients or documentation; configure the production API origin through the deployment environment.

Versioned application routes are served below `/api/v1`. OpenAPI is available at `/docs` and `/openapi.json` only when enabled by the deployment policy.

## Request flow

Clients call `/api/v1/{resource}`. The router validates the request with a domain DTO, applies authentication/authorization dependencies, delegates business rules to the domain service, and returns the defined response contract. Clients never call repositories or Supabase directly.

## Operational endpoints

- `GET /health` — load-balancer/platform health check.
- `GET /api/v1/settings/` — authorized settings list.
- `PATCH /api/v1/settings/{key}` — authorized typed setting update.
- `POST /api/v1/settings/{key}/reset` — authorized setting reset.

## Authentication and authorization

Authentication establishes the server-verified subject. Authorization is enforced by server-side policy/RBAC and ownership checks. Client-supplied role, user ID, or permission fields are not trusted for access decisions.

## Error handling

Use the HTTP status and stable public error contract returned by the API. The API must never expose stack traces, database errors, provider responses, credentials, tokens, or sensitive internal identifiers to clients. Authentication and authorization failures remain intentionally generic.

## Compatibility

Existing public paths and response envelopes are treated as contracts. Breaking changes require an explicit API version or documented migration. Internal repository, service, and database implementation details are not public API contracts.

## Production client rules

Use HTTPS in production, send only required fields, honor pagination and rate-limit responses, preserve request/correlation IDs when troubleshooting, and never persist server-only credentials in browser code.
