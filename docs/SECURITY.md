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

## Checkout data ownership and lookup rules

- Profile and saved-address email values are validated at the API boundary with `EmailStr`.
- Checkout reads the selected address from the database and snapshots the validated email/address into the order; payment confirmation uses that immutable snapshot, not mutable profile data.
- Stripe remains the source of truth for payment status and amount; the database RPC is the source of truth for order settlement, stock reservation, and idempotency.
- Webhooks must be signature-verified and claimed by event ID before settlement. Client confirmation is a recovery path, never proof of payment by itself.
- Public catalog/pricing reads may be cached at runtime; stock, coupons, authorization, orders, and payment state must be fresh database/provider lookups.
- Payment webhooks select only required order columns and never use wildcard projections for sensitive records.

## Fresh commit validation

The latest domain changes were validated with 36 passing tests. Test-only Supabase and Stripe placeholders are loaded before module collection; production configuration still fails closed when required credentials are missing. The remaining five warnings originate in third-party Supabase and ReportLab packages and are not application failures.
