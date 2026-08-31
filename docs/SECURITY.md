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

Before every release, run the checks in `docs/ARCHITECTURE.md`, review changed routes and confirm no secret-like value appears in the diff.
