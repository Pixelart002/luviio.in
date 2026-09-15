# Luviio Payments: Provider-Neutral Architecture

## Scope

This document defines the payment boundary used by checkout, retries, settlement,
webhooks, refunds, and abandoned-order reconciliation.

## Runtime flow

```text
HTTP Router
   |
   v
PaymentService
   |
   +--> PaymentPolicy
   |
   +--> PaymentPluginManager / provider registry
   |       |
   |       +--> installed provider implementation
   |       +--> DB-enabled provider/method configuration
   |
   +--> AsyncPaymentRepository
           |
           +--> provider-neutral payment RPCs
                   |
                   +--> orders
                   +--> payments
                   +--> payment_attempts
                   +--> payment_retry_reservations
                   +--> webhook_events_ledger
                   +--> inventory settlement
```

## Payment identity

New runtime writes use the pair:

```text
payment_provider
provider_payment_id
```

The legacy Stripe columns remain temporarily for historical compatibility and
replay safety. They are not the authoritative provider identity for new code.

Existing Stripe records are backfilled by migration:

```text
orders.stripe_payment_intent
        -> orders.payment_provider = stripe
        -> orders.provider_payment_id

payments.stripe_payment_intent_id
        -> payments.payment_provider = stripe
        -> payments.provider_payment_id
```

## Compatibility policy

Legacy function signatures remain available because existing application paths
may still call them. They now resolve provider identity from the payment ledger
and delegate to provider-neutral functions.

This allows a rolling deployment without rewriting historical data in place.

## Provider registration policy

Runtime admin APIs may enable, disable, register, and remove only providers that
are already trusted application plugins. Admin APIs never upload or execute
arbitrary Python code.

Removing a provider deletes only its runtime configuration. Historical payment
rows remain intact because payment identity is stored on the payment/order data.

## Settlement invariant

Payment success is authoritative for payment settlement. The order is not
allowed to become `paid` solely because a client says payment succeeded.

Settlement validates:

- authenticated customer ownership
- provider identity
- provider payment reference
- order/payment binding
- amount
- currency
- terminal order status

A cancelled order cannot be resurrected by a late successful callback. The
existing provider-specific Stripe functions remain only as compatibility/replay
paths until they are retired deliberately.

## Migration order

Apply migrations in repository order. The relevant new sequence is:

1. `20260915200000_provider_neutral_payment_identity.sql`
2. `20260915213000_complete_provider_neutral_payment_runtime.sql`
3. `20260915214500_route_legacy_payment_rpcs_through_provider_identity.sql`
4. `20260915220000_harden_provider_neutral_checkout_rpc.sql`

Production deployment must not ship application code that expects the new RPCs
before these migrations are applied.
