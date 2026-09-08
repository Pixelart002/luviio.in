# Production Security Baseline

## Required controls

- Keep `SB_SERVICE_ROLE_KEY` server-side only.
- Use allowlisted CORS origins; never combine credentialed requests with `*`.
- Validate request bodies with Pydantic domain DTOs.
- Authorize with server-verified identity, RBAC/policy, and ownership checks; never trust user-editable role or permission metadata.
- Select only required database columns and never expose secrets, tokens, or payment credentials in logs.
- Verify Stripe and other webhook signatures before processing business events.
- Preserve webhook idempotency and payment settlement integrity across retries and concurrent delivery.
- Rate-limit authentication and mutation endpoints and enforce request/body limits.
- Return safe generic errors to clients; keep provider/database details in redacted server logs.
- Keep debug/admin documentation and operational endpoints reviewed before public exposure.
- Rotate credentials through deployment secret management, never through source files.

## Logging and observability

Request and correlation IDs must be sanitized and safe to return to clients. Production logs must be structured and redacted. Do not log authorization headers, cookies, service-role keys, Stripe secrets, webhook secrets, VAPID private keys, passwords, client secrets, or raw sensitive payloads.

## External integrations

Provider adapters must use bounded network timeouts and explicit failure handling. Transient provider failures may be retried with bounded backoff; permanent resource-invalid responses may be cleaned up only when the provider explicitly establishes that the resource is no longer valid. Do not delete recoverable subscriptions or business records merely because one delivery attempt failed.

## Database security

RLS remains enabled where applicable. Privileged database functions use explicit execution permissions and controlled search paths. Payment settlement and webhook claim operations rely on database-backed integrity and idempotency rather than application-process locks.

## Change hygiene

Delete stale code only after its replacement is committed, all imports are migrated, tests cover the behavior, and a tracked-file/import scan shows no consumers. Do not maintain a second implementation behind a compatibility alias.

## Release validation

Before production release, run the CI verification gates, review the complete diff for secret-like values, confirm migrations are reviewed, and verify that environment-specific credentials are supplied only by the deployment platform. Security warnings from third-party dependencies must be tracked separately from application failures and must not be misreported as application defects.
