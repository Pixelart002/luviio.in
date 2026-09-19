begin;

create table if not exists public.shipping_shipments (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete restrict,
  provider_key text not null,
  external_order_id text,
  external_shipment_id text,
  tracking_number text,
  courier_name text,
  status text not null default 'created',
  tracking_url text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_shipping_shipments_order_provider
  on public.shipping_shipments(order_id, provider_key);

create index if not exists idx_shipping_shipments_tracking
  on public.shipping_shipments(tracking_number);

create index if not exists idx_shipping_shipments_status
  on public.shipping_shipments(status);

alter table public.shipping_shipments enable row level security;

drop policy if exists "shipping_shipments_no_direct_client_access" on public.shipping_shipments;
create policy "shipping_shipments_no_direct_client_access"
  on public.shipping_shipments
  for all
  to anon, authenticated
  using (false)
  with check (false);

grant select, insert, update, delete on public.shipping_shipments to service_role;

commit;
