alter table public.notification_dlq
    add column if not exists subscription_endpoint text;

create index if not exists idx_notification_dlq_retry_due
    on public.notification_dlq (status, next_retry_at, created_at);

create index if not exists idx_notification_dlq_endpoint
    on public.notification_dlq (subscription_endpoint);
