# API Guide

## Base URL

Local: `https://apparent-jordanna-pixelart002-42e39ac6.koyeb.app`  
Production: use the deployed API origin.

OpenAPI is available at `/docs` and `/openapi.json` when enabled by deployment policy.

## Request flow

Clients call `/api/v1/{resource}`. The router validates the request with a DTO, checks authorization, delegates to a service, and returns the existing response envelope. Clients should not call repositories or Supabase directly.

## Operational endpoints

- `GET /health` — load balancer health check.
- `GET /api/v1/settings/` — authorized settings list.
- `PATCH /api/v1/settings/{key}` — authorized typed setting update.
- `POST /api/v1/settings/{key}/reset` — restore a setting default.

## Error handling

Use the HTTP status and stable message returned by the API. Do not expose stack traces, database errors, provider responses or secrets to clients. Authentication and authorization failures must remain generic.

## Compatibility rule

Existing paths and response envelopes are preserved. New behavior must be additive or use an explicit version/compatibility alias.
