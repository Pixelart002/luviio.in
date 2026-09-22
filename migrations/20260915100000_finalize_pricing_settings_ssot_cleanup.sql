-- Final pricing-settings cleanup.
-- system_settings is the sole source of global checkout pricing configuration.
-- The legacy pricing_config compatibility layer is permanently removed.

drop trigger if exists trg_sync_pricing_config_from_system_settings on public.system_settings;
drop function if exists public.sync_pricing_config_from_system_settings();
drop table if exists public.pricing_config;

create or replace function public.get_canonical_pricing_config()
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'tax_enabled', coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'tax_enabled' limit 1), true),
    'shipping_enabled', coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'shipping_enabled' limit 1), false),
    'currency', coalesce((select trim(both '"' from value::text) from public.system_settings where key = 'currency' limit 1), 'INR'),
    'shipping_flat', coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'flat_shipping_rate' limit 1), 0),
    'shipping_threshold', coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'free_shipping_threshold' limit 1), 0)
  );
$$;

revoke all on function public.get_canonical_pricing_config() from public;
grant execute on function public.get_canonical_pricing_config() to service_role;


-- Shiprocket is the checkout shipping SSOT. Remove legacy global flat/free-shipping
-- configuration so no stale amount can be used as a customer shipping price.
delete from public.system_settings
where key in ('shipping_enabled', 'flat_shipping_rate', 'free_shipping_threshold');
