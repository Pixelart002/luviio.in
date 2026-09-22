begin;

alter table public.shipping_shipments
  add column if not exists pickup_id text,
  add column if not exists label_url text,
  add column if not exists manifest_url text,
  add column if not exists provider_invoice_url text,
  add column if not exists pickup_scheduled_at timestamptz,
  add column if not exists shipped_at timestamptz,
  add column if not exists delivered_at timestamptz,
  add column if not exists provider_status text,
  add column if not exists last_provider_event_at timestamptz,
  add column if not exists failure_code text,
  add column if not exists failure_message text;

create index if not exists idx_shipping_shipments_external_shipment
  on public.shipping_shipments(external_shipment_id);
create index if not exists idx_shipping_shipments_awb
  on public.shipping_shipments(tracking_number);
create index if not exists idx_shipping_shipments_provider_status
  on public.shipping_shipments(provider_key, provider_status);

create table if not exists public.shipping_shipment_events (
  id uuid primary key default gen_random_uuid(),
  shipment_id uuid not null references public.shipping_shipments(id) on delete cascade,
  provider_event_id text not null,
  provider_status text not null,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (provider_event_id)
);

create index if not exists idx_shipping_shipment_events_shipment
  on public.shipping_shipment_events(shipment_id, occurred_at desc);

alter table public.shipping_shipment_events enable row level security;
drop policy if exists "shipping_shipment_events_no_direct_client_access" on public.shipping_shipment_events;
create policy "shipping_shipment_events_no_direct_client_access"
  on public.shipping_shipment_events
  for all to anon, authenticated
  using (false) with check (false);
grant select, insert, update, delete on public.shipping_shipment_events to service_role;

commit;
