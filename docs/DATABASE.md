# Database Guide

Supabase is the persistence boundary. Database access belongs in domain repositories or approved infrastructure repositories; routers and external clients must not access Supabase directly.

## Production rules

- Keep Row Level Security enabled on exposed tables.
- Scope user-owned reads and writes by the authenticated subject.
- Treat service-role access as server-only privileged access.
- Use explicit column projections; never use `select *` for sensitive data.
- Validate filters and mutation inputs before persistence.
- Keep schema changes in reviewed, ordered migrations.
- Use database constraints, transactions, unique keys, and RPCs for correctness-critical operations.
- Add indexes for proven query patterns and validate their benefit against production workload before removing them.
- Test anonymous, authenticated, and privileged access paths where RLS applies.

## Payments, orders, and inventory

Payment settlement, webhook idempotency, order state transitions, and inventory correctness must not depend on process-local memory or locks. Database-backed constraints and transactional functions are the source of truth for concurrent requests and retries.

## Migrations

Every schema or database-function change must be represented by a migration and reviewed before deployment. Production migration history is append-only; do not edit an already-applied migration to change production behavior. Add a new corrective migration instead.

## Secrets

Never expose `SB_SERVICE_ROLE_KEY` or provider credentials to clients, source control, logs, or database records. Environment/deployment secret management is the only supported location for server credentials.

## Settings

`system_settings` contains operational configuration, not business records. Do not use it as a replacement for orders, products, users, payment records, RBAC policy, or high-frequency counters. See `docs/SETTINGS.md` for the settings contract.
