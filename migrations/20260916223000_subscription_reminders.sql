-- Subscription lifecycle reminders.
-- One row per subscription/reminder type guarantees DB-level deduplication.
create table if not exists public.subscription_reminders (
    id uuid primary key default gen_random_uuid(),
    subscription_id uuid not null references public.user_subscriptions(id) on delete cascade,
    user_id uuid not null references public.users(id) on delete cascade,
    reminder_type text not null check (reminder_type in ('7d', '1d', 'expired')),
    due_at timestamptz not null,
    title text not null,
    body text not null,
    status text not null default 'pending' check (status in ('pending', 'processing', 'sent', 'dismissed')),
    created_at timestamptz not null default now(),
    sent_at timestamptz,
    dismissed_at timestamptz,
    unique (subscription_id, reminder_type)
);

create index if not exists idx_subscription_reminders_user_status
    on public.subscription_reminders(user_id, status, created_at desc);

create index if not exists idx_subscription_reminders_due_status
    on public.subscription_reminders(due_at, status);

alter table public.subscription_reminders enable row level security;

-- Customers may read and dismiss only their own reminder rows.
drop policy if exists subscription_reminders_select_own on public.subscription_reminders;
create policy subscription_reminders_select_own
    on public.subscription_reminders
    for select
    to authenticated
    using (user_id = auth.uid());

drop policy if exists subscription_reminders_update_own on public.subscription_reminders;
create policy subscription_reminders_update_own
    on public.subscription_reminders
    for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- No client inserts/deletes. The backend admin client creates lifecycle reminders.
