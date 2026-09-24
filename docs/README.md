# Luviio Backend Documentation Index

Last reviewed: 2026-09-24
Source of truth: current `main` backend codebase.

## Read in this order

### Architecture
1. [`SYSTEM_MAP.md`](SYSTEM_MAP.md) — complete backend architecture, domain ownership and runtime boundaries.
2. [`DEPENDENCY_GRAPH.md`](DEPENDENCY_GRAPH.md) — Python dependencies and domain dependency direction.

### Contracts
3. [`API_REFERENCE.md`](API_REFERENCE.md) — complete HTTP inventory, access class and workflow role.
4. [`DATA_SECURITY.md`](DATA_SECURITY.md) — authorization, ownership, database boundaries and sensitive-data rules.
5. [`DATABASE.md`](DATABASE.md) — persistence and database invariants.

### Workflows
6. [`USER_FLOWS.md`](USER_FLOWS.md) — backend customer lifecycle.
7. [`ADMIN_FLOWS.md`](ADMIN_FLOWS.md) — backend operator lifecycle.
8. [`BACKGROUND_WORKFLOWS.md`](BACKGROUND_WORKFLOWS.md) — events, cron, outbox, notifications and retry paths.
9. [`FULFILLMENT_WORKFLOW.md`](FULFILLMENT_WORKFLOW.md) — shipping/fulfillment lifecycle.

### Operations
10. [`OPERATIONS.md`](OPERATIONS.md) — CI, health, deploy, smoke test and rollback.
11. [`TESTING.md`](TESTING.md) — automated test strategy and CI gates.
12. [`DEPLOYMENT.md`](DEPLOYMENT.md) — backend release/deployment rules.
13. [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) — verified state and remaining operational gates.

## Documentation rule

Documentation is implementation-owned. A backend route, API contract, permission, workflow, database invariant, deployment step or operator action is not considered fully changed until its matching backend source-of-truth documentation is updated in the same change.

## Workflow ownership

```text
Backend architecture   -> SYSTEM_MAP.md
Backend API contract   -> API_REFERENCE.md
Customer backend flow  -> USER_FLOWS.md
Admin backend flow     -> ADMIN_FLOWS.md
Async/event processing -> BACKGROUND_WORKFLOWS.md
Fulfillment           -> FULFILLMENT_WORKFLOW.md
Operations            -> OPERATIONS.md / DEPLOYMENT.md
```

The browser frontend is intentionally outside this repository. Browser UI/acceptance assets belong to the separate frontend codebase.
