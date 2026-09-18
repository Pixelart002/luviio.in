-- Backfill first-class refund-history rows from the already-accounted refund ledger.
-- Historical Stripe refund IDs were not retained in the old ledger, so they remain
-- NULL here rather than inventing a provider object identifier.
insert into public.payment_refunds(
    payment_id,
    order_id,
    refund_attempt_number,
    payment_provider,
    provider_payment_id,
    provider_refund_id,
    idempotency_key,
    amount,
    amount_paise,
    currency,
    status,
    reason,
    reference,
    gateway_metadata,
    requested_at,
    processed_at,
    created_at,
    updated_at
)
select
    l.payment_id,
    l.order_id,
    1,
    l.provider,
    l.provider_payment_id,
    null,
    'legacy-ledger:' || l.id::text,
    l.amount,
    l.amount_paise,
    l.currency,
    'succeeded',
    'legacy_backfill',
    'legacy-ledger:' || l.id::text,
    coalesce(l.metadata, '{}'::jsonb) || jsonb_build_object(
        'source', 'legacy_backfill',
        'original_ledger_id', l.id,
        'original_reference', l.reference,
        'provider_refund_id_unavailable', true
    ),
    coalesce(l.created_at, now()),
    coalesce(l.created_at, now()),
    coalesce(l.created_at, now()),
    now()
from public.payment_ledger l
join public.payments p on p.id = l.payment_id
join public.orders o on o.id = l.order_id
where l.entry_type = 'payment_refunded'
  and o.status = 'refunded'
  and not exists (
      select 1
      from public.payment_refunds r
      where r.payment_id = l.payment_id
  )
on conflict (payment_id, refund_attempt_number) do nothing;
