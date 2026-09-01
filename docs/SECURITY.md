# Security Baseline

- Keep `SB_SERVICE_ROLE_KEY` server-side only.
- Use allowlisted CORS origins; never use `*` with credentials.
- Validate request bodies with Pydantic DTOs.
- Authorize by server-verified role/policy, never by user-editable metadata.
- Select only required database columns; never expose secrets or tokens in logs.
- Verify Stripe and other webhook signatures before parsing business events.
- Rate-limit authentication, checkout and mutation endpoints.
- Return safe generic errors to clients; keep provider/database details in redacted server logs.
- Keep production docs and debug endpoints reviewed before exposure.
- Rotate credentials through deployment environment management, never source files.

## Release controls

Before every release, run the checks in `docs/ARCHITECTURE.md`, review changed routes and confirm no secret-like value appears in the diff. Treat `SB_SERVICE_ROLE_KEY` as a privileged server-only credential: never return it, log it, place it in client code, or use it to bypass an authorization decision. Keep authorization checks close to the service boundary, use explicit column projections, and fail closed for privileged mutations.

## Cleanup rule

Delete stale code only after its replacement is committed, all imports are migrated, tests cover the behavior, and a tracked-file/import scan shows no consumers. Compatibility adapters may remain temporarily, but they must contain delegation only—not a second business-logic implementation. Best-effort cleanup paths (thumbnail rollback, remote cancellation, queue delivery) now emit safe server logs instead of silently swallowing failures; provider details and secrets are never returned to clients.
