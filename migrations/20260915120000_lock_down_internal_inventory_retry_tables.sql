-- These tables are backend/service-role infrastructure. They are not part of
-- the browser-facing data contract and intentionally have no client policies.
alter table public.stock_audit enable row level security;
alter table public.payment_retry_reservations enable row level security;
alter table public.payment_retry_policy enable row level security;

revoke all on table public.stock_audit from anon, authenticated;
revoke all on table public.payment_retry_reservations from anon, authenticated;
revoke all on table public.payment_retry_policy from anon, authenticated;

grant all on table public.stock_audit to service_role;
grant all on table public.payment_retry_reservations to service_role;
grant all on table public.payment_retry_policy to service_role;
