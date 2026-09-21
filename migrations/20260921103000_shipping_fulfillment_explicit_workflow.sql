begin;

alter table public.shipping_shipments
  add column if not exists courier_id bigint,
  add column if not exists service_type text,
  add column if not exists workflow_status text,
  add column if not exists awb_assigned_at timestamptz,
  add column if not exists pickup_requested_at timestamptz,
  add column if not exists manifest_generated_at timestamptz,
  add column if not exists label_generated_at timestamptz,
  add column if not exists provider_invoice_generated_at timestamptz;

alter table public.shipping_shipments
  drop constraint if exists shipping_shipments_workflow_status_check;

alter table public.shipping_shipments
  add constraint shipping_shipments_workflow_status_check
  check (
    workflow_status is null or workflow_status = any (array[
      'ready_to_create','created','awb_assigned','pickup_scheduled',
      'manifest_generated','label_generated','invoice_generated',
      'documents_ready','shipped','delivered','cancelled','failed'
    ])
  );

update public.shipping_shipments
set
  courier_id = coalesce(courier_id, nullif((metadata->'selected_courier'->>'courier_id'), '')::bigint),
  service_type = coalesce(service_type, nullif(metadata->'selected_courier'->>'service_type', '')),
  workflow_status = case
    when delivered_at is not null then 'delivered'
    when shipped_at is not null then 'shipped'
    when failure_message is not null or status = 'failed' then 'failed'
    when provider_invoice_url is not null then 'documents_ready'
    when label_url is not null then 'label_generated'
    when manifest_url is not null then 'manifest_generated'
    when pickup_id is not null then 'pickup_scheduled'
    when tracking_number is not null then 'awb_assigned'
    else 'created'
  end,
  awb_assigned_at = case when tracking_number is not null and awb_assigned_at is null then updated_at else awb_assigned_at end,
  manifest_generated_at = case when manifest_url is not null and manifest_generated_at is null then updated_at else manifest_generated_at end,
  label_generated_at = case when label_url is not null and label_generated_at is null then updated_at else label_generated_at end,
  provider_invoice_generated_at = case when provider_invoice_url is not null and provider_invoice_generated_at is null then updated_at else provider_invoice_generated_at end;

create index if not exists idx_shipping_shipments_workflow_status
  on public.shipping_shipments(workflow_status);

create index if not exists idx_shipping_shipments_courier
  on public.shipping_shipments(provider_key, courier_id);

drop index if exists public.idx_shipping_shipments_tracking;

commit;