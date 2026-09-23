# Luviio Documentation Index

Last reviewed: 2026-09-24
Source of truth: current `main` codebase.

## Read in this order

### Architecture
1. [`SYSTEM_MAP.md`](SYSTEM_MAP.md) — complete backend architecture, domain ownership and runtime boundaries.
2. [`FRONTEND_SYSTEM_MAP.md`](FRONTEND_SYSTEM_MAP.md) — browser routes, frontend ownership and frontend↔backend boundaries.
3. [`DEPENDENCY_GRAPH.md`](DEPENDENCY_GRAPH.md) — Python dependencies and domain dependency direction.

### Contracts
4. [`API_REFERENCE.md`](API_REFERENCE.md) — complete HTTP inventory, access class and workflow role.
5. [`DATA_SECURITY.md`](DATA_SECURITY.md) — authorization, ownership, database boundaries and sensitive-data rules.
6. [`DATABASE.md`](DATABASE.md) — persistence and database invariants.

### Workflows
7. [`USER_FLOWS.md`](USER_FLOWS.md) — backend customer lifecycle.
8. [`ADMIN_FLOWS.md`](ADMIN_FLOWS.md) — backend operator lifecycle.
9. [`BROWSER_WORKFLOWS.md`](BROWSER_WORKFLOWS.md) — executable browser acceptance workflows linking UI actions to API/business outcomes.
10. [`BACKGROUND_WORKFLOWS.md`](BACKGROUND_WORKFLOWS.md) — events, cron, outbox, notifications and retry paths.
11. [`FULFILLMENT_WORKFLOW.md`](FULFILLMENT_WORKFLOW.md) — shipping/fulfillment lifecycle.

### Operations
12. [`OPERATIONS.md`](OPERATIONS.md) — CI, health, deploy, smoke test and rollback.
13. [`TESTING.md`](TESTING.md) — automated test strategy and CI gates.
14. [`DEPLOYMENT.md`](DEPLOYMENT.md) — release/deployment rules.
15. [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) — verified state and remaining operational gates.

## Documentation rule

Documentation is implementation-owned. A route, API contract, permission, workflow, database invariant, frontend state transition, deployment step or operator action is not considered fully changed until its matching source-of-truth documentation is updated in the same change.

## Workflow ownership

```text
Backend architecture       -> SYSTEM_MAP.md
Backend API contract       -> API_REFERENCE.md
Customer backend flow      -> USER_FLOWS.md
Admin backend flow         -> ADMIN_FLOWS.md
Frontend route/client map  -> FRONTEND_SYSTEM_MAP.md
Browser acceptance         -> BROWSER_WORKFLOWS.md
Async/event processing     -> BACKGROUND_WORKFLOWS.md
Fulfillment                -> FULFILLMENT_WORKFLOW.md
Production operations      -> OPERATIONS.md / DEPLOYMENT.md
```

The browser workflow document is the bridge between what a user does in the browser and what the backend must prove.
