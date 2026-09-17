# Luviio Backend Production Audit — 2026-09-17

## Scope

This audit covers the backend application, database security boundaries, domain architecture, CI, payment/inventory integrity, operational controls, and production release gates.

## Domain status

| Domain | Status | Remaining gate |
|---|---|---|
| Auth | GREEN | Supabase leaked-password protection configuration |
| Users / profiles / addresses | GREEN | routine regression |
| RBAC / ABAC | GREEN | maintain full matrix regression |
| Products / catalog | GREEN | current performance baseline |
| Categories | GREEN | smoke |
| Cart | GREEN | current performance baseline |
| Pricing | GREEN | smoke |
| Coupons | GREEN | live configured E2E |
| Inventory | GREEN | real concurrency validation |
| Orders | GREEN | full lifecycle smoke |
| Payments / Stripe | GREEN | live provider E2E |
| COD | GREEN | live smoke |
| Shipping | GREEN | boundary smoke |
| GST / tax | GREEN | seller statutory configuration |
| Invoices | GREEN | generated-PDF/statutory verification |
| Notifications | GREEN | provider E2E |
| Event outbox | GREEN | operational monitoring |
| Subscriptions | GREEN | only if business feature is activated |
| Reviews | GREEN | submit/moderation smoke |
| Admin | GREEN | full admin smoke |
| Settings | GREEN | documentation synchronization completed |
| Rate limiting | GREEN | monitor SLO |
| Cron / leases | GREEN | runtime observation |
| Business assets | GREEN | future orphan-object GC |
| DB / RLS / privileges | GREEN | periodic advisor review |
| Indexes | GREEN | do not delete without workload evidence |
| API routing | GREEN | complete route inventory regression |
| Error handling | GREEN | failure-injection verification |
| Observability | GREEN | production verification |
| Performance | AMBER | collect p50/p95/p99 |
| Dependencies | AMBER | controlled modernization |
| Test depth | AMBER | maintain critical-domain coverage |
| Documentation | GREEN | state/ledger synchronized in this audit |

## Security conclusions

The major server-authority boundaries are in place. Browser/client roles cannot directly mutate the principal server-owned commerce tables. Payment, coupon, inventory, and outbox mutation paths are service-role controlled. RBAC and per-user action controls fail closed when policy state is unavailable. Admin self-escalation and low-stock mutation/read permission boundaries are covered by targeted tests.

## Payment integrity

Payment confirmation, duplicate webhook delivery, concurrent confirmation, cancellation/refund compensation, retry convergence, and provider-persistence failure paths are represented in the payment race suite. PR #69 isolated checkout action-control in the affected test without weakening production fail-closed behavior and was merged after green CI.

## Database security

The current Supabase production advisor shows one security warning: leaked-password protection is disabled. This is an Auth configuration setting, not a PostgreSQL DDL issue, and must be enabled through Supabase Auth configuration before treating the security gate as fully closed.

## Index review

The performance advisor currently reports ten indexes as unused. This audit deliberately does not delete them. Unused-index telemetry can be misleading for new, low-traffic, or conditional workloads; deletion requires representative workload/query-plan evidence and a rollback path.

## Production smoke suite

Run against the deployed environment with test credentials/providers:

1. `/health/live`
2. `/health`
3. products
4. categories
5. login/session
6. cart read/write
7. shipping calculation
8. coupon application
9. COD checkout
10. Stripe test checkout + webhook
11. customer order lookup by `order_number`
12. invoice PDF generation
13. review submit/moderation
14. admin verification/dashboard
15. authorized settings mutation
16. RBAC effective permission matrix
17. share-card HTML/OG response
18. notification delivery
19. payment failure/refund retry
20. inventory concurrent settlement

## Release decision

No unresolved P0/P1 application defect is identified by this audit. The remaining release gates are external configuration, provider/live smoke testing, statutory business configuration, performance measurement, and a controlled dependency modernization pass.

These gates must not be represented as completed merely because the corresponding application code exists.
