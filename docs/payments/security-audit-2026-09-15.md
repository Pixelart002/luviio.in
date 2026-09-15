# Luviio Payment Security Audit — 15 Sep 2026

## Audit method

The audit was performed against the current `main` branch code and migration set,
not against assumptions from earlier revisions.

## Findings fixed

### P0 — Stripe-coupled payment persistence

The application already had provider context, plugin registry, provider toggles,
and provider-neutral columns, but critical persistence paths still depended on
Stripe-specific fields/RPC contracts.

Fixed by introducing provider-neutral identity and runtime RPCs for:

- order/payment identity
- payment attempts
- retry reservations
- webhook event claiming
- settlement
- abandoned-order provider selection
- refund provider selection

### P0 — Checkout payload validation

The provider-neutral order-creation RPC now rejects empty carts, non-positive or
oversized quantities, unavailable products, invalid currency, and non-positive
order totals before inventory mutation.

### P1 — Historical compatibility

Legacy Stripe columns remain populated for Stripe records and old RPC signatures
remain available. New provider-aware writes use the neutral identity fields.

### P1 — Provider removal safety

Admin removal is configuration-only and blocked while the provider is enabled or
still marked default. Historical payment records are preserved.

## Security invariants

```text
Client says "paid"
       X
       |
       v
Payment provider verification
       |
       v
Provider + payment-id binding
       |
       v
Amount + currency validation
       |
       v
Atomic settlement
       |
       v
Order -> paid
```

Duplicate webhooks remain idempotent through the webhook ledger. A late success
for a cancelled order remains terminal and must not recreate or resurrect the
order.

## Remaining security hardening

### Trusted proxy handling

The payment router currently derives the rate-limit key from `X-Forwarded-For`.
That header must only be trusted when the request came through an explicitly
configured trusted proxy. Otherwise a direct client can spoof the value and
rotate rate-limit buckets.

Recommended final hardening:

```text
trusted proxy -> accept forwarded client address
untrusted direct client -> use request.client.host
```

This is intentionally documented separately from the payment identity migration
so proxy topology can be configured correctly for the production deployment.

## Production migration gate

Before deploying the application version that calls the new provider-neutral RPCs:

1. Apply all four provider-neutral payment migrations in order.
2. Verify the functions exist and are executable only by `service_role`.
3. Verify existing Stripe rows were backfilled.
4. Run provider-neutral payment integration tests.
5. Only then promote the application deployment.

The repository changes alone do not prove that production Supabase has already
applied these migrations.
