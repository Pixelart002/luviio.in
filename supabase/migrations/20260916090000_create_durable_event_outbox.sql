create table if not exists public.event_outbox (
    id uuid primary key default gen_random_uuid(),
    event_type text not null,
    payload jsonb not null,
    status text not null default 'pending' check (status in ('pending','processing','completed','failed')),
    attempts integer not null default 0 check (attempts >= 0),
    next_retry_at timestamptz not null default now(),
    locked_at timestamptz,
    last_error text,
    created_at timestamptz not null default now(),
    processed_at timestamptz
);

create index if not exists idx_event_outbox_dispatch
    on public.event_outbox (status, next_retry_at, created_at);

create index if not exists idx_event_outbox_locked
    on public.event_outbox (status, locked_at);

alter table public.event_outbox enable row level security;
revoke all on table public.event_outbox from anon, authenticated;
grant all on table public.event_outbox to service_role;
