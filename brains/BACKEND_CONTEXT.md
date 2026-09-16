# Luviio Backend Brain

## Purpose
This file is the persistent engineering context for backend hardening work. It is not runtime configuration and must never contain secrets.

## Canonical architecture
```text
Browser
  -> FastAPI /api/v1
     -> domain router
        -> service / policy
           -> repository
              -> Supabase/Postgres

Payments
  -> provider adapter
  -> webhook signature verification
  -> DB settlement RPC / ledger

Correctness-critical state
  -> database constraints + transactional RPCs
  -> process memory is never the source of truth

Events
  -> transactional outbox
  -> durable dispatcher
  -> email/push handlers
```

## Hard boundaries
- Browser must not mutate `users`, `addresses`, `carts`, `cart_items`, or `orders` directly through Supabase REST.
- FastAPI service-role operations are the mutation boundary for those tables.
- RLS remains defense-in-depth, not the business authorization layer.
- `role`, `is_active`, payment state, order totals, invoice identifiers, and cart price snapshots are server-owned.
- Checkout price is derived from a server-created cart snapshot.
- Coupon reservation and inventory reservation must be atomic with pending-order creation.
- Payment settlement must be idempotent and database-backed.
- Immutable invoice snapshots are the source for issued invoice PDFs.

## Current production invariants
- Customer-facing order number is unique and separate from internal UUID.
- Coupon reservation happens inside the pending-order transaction.
- Coupon redemption is recorded only on successful settlement.
- Cancelled checkout releases inventory and coupon reservations.
- Payment success after cancellation must not resurrect the order.
- Trigger-only outbox functions are service-role-only.
- Auth brute-force throttling is database-backed and shared across workers.

## Known operational constraints
- Koyeb connector is not available in ChatGPT; deployment status must not be claimed without logs or external verification.
- Supabase project is the canonical production database.
- Do not put secrets, tokens, legal identifiers, or customer PII in this directory.

## Engineering rule
Prefer one transactional source of truth over orchestration spread across multiple asynchronous requests. When a rule changes money, stock, identity, or access control, enforce it at the database boundary as well as in Python.
