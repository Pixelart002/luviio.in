# Background Workflows

Last reviewed: 2026-09-16

## Startup lifecycle

```text
Process starts
  -> configure logging
  -> initialize Sentry when configured
  -> FastAPI lifespan starts
       -> register_all_event_handlers()
       -> start_cron_jobs()
  -> serve requests
  -> lifespan shutdown
```

The startup event bus is currently in-process. The database outbox table can hold durable work, but durable delivery is only authoritative once event enqueue/claim/delivery semantics are wired transactionally.

## Event workflow

```text
Domain mutation
   |
   v
Business event
   |
   +--> in-process EventBus (current runtime path)
   |
   +--> durable outbox (storage exists; delivery path must remain idempotent)
              |
              v
        worker/cron claim
              |
       +------+------+
       |             |
    success       transient failure
       |             |
 processed_at    next_retry_at/backoff
                     |
                 exhausted -> DLQ/ops visibility
```

## Order/payment workflow

```text
Checkout
  -> order pending
  -> inventory stock operation
  -> payment attempt
  -> provider
       | success
       v
 payment settlement
  -> ledger/attempt state
  -> order payment state
  -> inventory finalization
  -> invoice snapshot
  -> notification/event
```

Failures must be idempotent. A duplicate client confirmation and duplicate webhook must converge instead of creating a second settlement.

## Cancellation/release workflow

```text
Pending order
   |
   +--> customer payment cancellation
   +--> stale-order release job
   +--> explicit order cancellation
            |
            v
      provider cancellation if needed
            |
            v
      inventory restoration once
            |
            v
      cancelled terminal state
```

The restoration operation must be safe when invoked repeatedly after a race.

## Low-stock workflow

```text
stock mutation
   |
   v
low-stock evaluation
   |
   +--> GET /inventory/low-stock (read)
   +--> POST /inventory/low-stock/scan
            |
            v
       publish alerts/events
            |
            v
       Push/email consumer
```

## Push workflow

```text
browser permission/subscription
  -> POST /push/subscribe
  -> subscription persistence
  -> domain event or test send
  -> PushService
  -> WebPush provider
  -> invalid subscription cleanup / operational failure record
```

## Scheduler responsibilities

The scheduler is started from `app.main` and owns retry-safe periodic jobs defined in `app/cron`. Jobs must be idempotent and safe to run again after process restarts. A scheduled job must not assume it is the only worker unless the implementation explicitly takes a DB/distributed lock.

## External provider failure model

```text
provider call
   |
   +--> success -> persist result
   |
   +--> timeout/transient -> bounded retry where safe
   |
   +--> permanent/invalid -> persist failure + user-safe error
   |
   +--> unknown -> reconciliation path / operator visibility
```

Payments require special handling because the provider may complete after the HTTP request has timed out. The webhook/reconciliation path is therefore part of the authoritative state machine.

## Operational warning

Current code exposes low-stock scan and stale-order release routes. Until a deployment-specific network trust boundary is guaranteed, these operational actions should be protected by explicit authorization and/or a trusted scheduler rather than left publicly triggerable.
