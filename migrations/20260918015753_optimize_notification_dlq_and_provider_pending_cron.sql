create index if not exists idx_notification_dlq_failed_due_created
  on public.notification_dlq (next_retry_at, created_at)
  where status = 'failed' and next_retry_at is not null;

create index if not exists idx_orders_pending_provider_created_at
  on public.orders (created_at)
  where status = 'pending'
    and (provider_payment_id is not null or stripe_payment_intent is not null);
