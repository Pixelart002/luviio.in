# Data, Security and Authorization Map

Last reviewed: 2026-09-16

## Trust zones

```text
UNTRUSTED
Browser / client input
   |
   v
TRANSPORT TRUST BOUNDARY
DTO validation + auth/session + rate limits
   |
   v
APPLICATION TRUST ZONE
Domain services + policy + repositories
   |
   +--> provider adapters
   |
   v
DATA TRUST ZONE
Supabase/Postgres / service-role access / RLS
```

## Authentication

Auth uses secure HttpOnly cookies for access/refresh session state. Session extraction is centralized in core dependencies. Password recovery is not considered complete merely because a frontend reset form exists; the server verifies the recovery context.

## Authorization model

Luviio uses a layered model:

1. Authentication establishes principal identity.
2. Permission dependencies enforce capability-level access.
3. Ownership/ABAC logic scopes records to the authenticated user where appropriate.
4. Domain policy enforces action-specific business constraints.
5. Database constraints/RLS must remain a final defense where public/client access can reach the table.

Examples:

```text
Customer order read
  -> authenticated user
  -> order.customer_id == session user_id

Admin order update
  -> authenticated admin
  -> orders:update
  -> state/payment policy

RBAC mutation
  -> admin:manage_roles
  -> target role manageable by actor
  -> self-lockout policy check
```

## Sensitive data rules

Never return or log:

- access/refresh tokens
- passwords or password-reset secrets
- Supabase service-role credentials
- Stripe/provider secrets
- raw payment credentials
- unnecessary personal data
- internal database UUIDs when a customer-facing identifier already exists

Use sanitized request/correlation IDs for tracing.

## Payment security

The browser may report a payment intent ID, but the backend verifies provider state. Webhooks use provider signatures. Confirmation and webhook processing must converge on one order/payment state without double settlement.

## Inventory security/integrity

Stock mutations are privileged. Customer cart writes are scoped to the current customer. Checkout is the authoritative place for final stock/price validation. Cancellation/restoration must be idempotent so repeated requests cannot create stock.

## Database boundary

Application repositories should use explicit projections and scoped filters. Server/admin Supabase clients remain server-only. Do not treat a service-role query as equivalent to an RLS policy; they are different trust boundaries.

Before enabling or changing RLS on a table:

1. identify every application read/write path;
2. map anonymous, owner, non-owner and privileged use cases;
3. define least-privilege policies;
4. verify server-only paths still work with their intended client;
5. run regression tests and a database security review.

Do not blindly enable RLS on tables used by runtime adapters.

## Auditability

High-impact admin actions should leave an auditable actor/action/reason trail. Payment events, order transitions, settings mutations and RBAC changes must remain diagnosable without exposing secrets.

## Security review checklist

```text
[ ] every route has explicit access class
[ ] every customer resource has ownership enforcement
[ ] every admin mutation has a permission
[ ] every payment webhook verifies signature
[ ] every money mutation has idempotency/concurrency rules
[ ] every stock mutation is audited
[ ] sensitive columns are not projected unnecessarily
[ ] service-role key is server-only
[ ] rate limits are applied to abuse-prone endpoints
[ ] operational endpoints cannot be triggered by arbitrary public traffic
[ ] RLS policy matches actual client/runtime access
```
