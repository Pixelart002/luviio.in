# Luviio Backend Documentation Index

Last reviewed: 2026-09-16
Source of truth: current `main` codebase.

## Read in this order

1. [`SYSTEM_MAP.md`](SYSTEM_MAP.md) — complete architecture, layers, domain ownership, runtime boundaries.
2. [`DEPENDENCY_GRAPH.md`](DEPENDENCY_GRAPH.md) — Python packages, domain-to-domain dependencies, external integrations, and dependency direction rules.
3. [`API_REFERENCE.md`](API_REFERENCE.md) — complete HTTP inventory, grouped by domain, with access class and workflow role.
4. [`USER_FLOWS.md`](USER_FLOWS.md) — customer lifecycle from session to catalog, cart, checkout, order, payment, invoice, review and notifications.
5. [`ADMIN_FLOWS.md`](ADMIN_FLOWS.md) — admin/operator flows for catalog, users, orders, payments, inventory, coupons, shipping, settings, RBAC, reviews and observability.
6. [`DATA_SECURITY.md`](DATA_SECURITY.md) — authorization, ownership, database boundary, RLS assumptions, sensitive data rules and audit behavior.
7. [`BACKGROUND_WORKFLOWS.md`](BACKGROUND_WORKFLOWS.md) — startup, event bus, cron, low-stock, stale-order release, notifications and failure/retry paths.
8. [`OPERATIONS.md`](OPERATIONS.md) — CI/CD, health checks, deployment, smoke tests, rollback and production verification.

## Existing detailed guides

- [`ARCHITECTURE.md`](ARCHITECTURE.md)
- [`API.md`](API.md)
- [`DATABASE.md`](DATABASE.md)
- [`SECURITY.md`](SECURITY.md)
- [`SETTINGS.md`](SETTINGS.md)
- [`TESTING.md`](TESTING.md)
- [`DEPLOYMENT.md`](DEPLOYMENT.md)
- [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md)

## Documentation rule

Documentation is implementation-owned. When a developer changes a route, domain contract, dependency, workflow, permission, database invariant, deployment step or operator action, the matching documentation file must be updated in the same change.

## Counts in this repository

- 15 feature/domain router families under `/api/v1`: Admin, Auth, Cart, Coupons, Inventory, Notifications, Orders, Payments, Products, RBAC, Reviews, Settings, Shipping, Subscriptions and Users.
- Health is infrastructure-owned and composed into both root and versioned API mounts.
- Social share is infrastructure-owned and mounted at the root application level.
- 105 distinct route handlers are defined across the current router modules.
- The root application adds one `/` handler, bringing the distinct application handlers to 106.
- Because the health router is mounted both outside and inside `/api/v1`, there are 108 concrete URL registrations in the FastAPI application.

## Important distinction

A route handler is a Python endpoint function. A URL registration is a concrete path mounted in FastAPI. The two numbers differ because health is intentionally exposed at both `/health*` and `/api/v1/health*`.
