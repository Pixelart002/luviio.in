-- Persist the delivery product metadata selected from the provider quote.
-- Quick/hyperlocal vehicle data is only populated when the provider actually
-- returns it; standard courier "Surface/Air" is not treated as a vehicle type.

alter table public.orders
  add column if not exists shipping_delivery_mode text,
  add column if not exists shipping_vehicle_type text;

alter table public.shipping_shipments
  add column if not exists delivery_mode text,
  add column if not exists vehicle_type text;

create index if not exists idx_orders_shipping_delivery_mode
  on public.orders (shipping_delivery_mode);

create index if not exists idx_shipping_shipments_vehicle_type
  on public.shipping_shipments (vehicle_type);
