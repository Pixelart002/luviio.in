-- Persist the customer-selected live Shiprocket courier on the order snapshot.
-- The checkout API revalidates the courier against fresh serviceability data before
-- writing these fields, so the order remains tied to the exact service the customer chose.

begin;

alter table public.orders
  add column if not exists shipping_provider text,
  add column if not exists shipping_courier_id bigint,
  add column if not exists shipping_courier_name text,
  add column if not exists shipping_service_type text;

create index if not exists idx_orders_shipping_courier
  on public.orders(shipping_provider, shipping_courier_id);

commit;
