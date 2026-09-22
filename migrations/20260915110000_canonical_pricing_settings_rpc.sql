-- Canonical pricing configuration boundary.
-- system_settings is the SSOT; pricing_config remains only as a temporary
-- compatibility projection during the migration away from direct table reads.

create or replace function public.get_canonical_pricing_config()
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'tax_enabled', coalesce((select value::boolean from public.system_settings where key = 'tax_enabled' limit 1), true),
    'shipping_enabled', coalesce((select value::boolean from public.system_settings where key = 'shipping_enabled' limit 1), true),
    'currency', coalesce((select value::text from public.system_settings where key = 'currency' limit 1), 'INR'),
    'shipping_flat', coalesce((select value::numeric from public.system_settings where key = 'flat_shipping_rate' limit 1), 0),
    'shipping_threshold', coalesce((select value::numeric from public.system_settings where key = 'free_shipping_threshold' limit 1), 0)
  );
$$;

revoke all on function public.get_canonical_pricing_config() from public;
grant execute on function public.get_canonical_pricing_config() to service_role;
