begin;

-- GST must be charged only when the seller is actually GST registered.
-- Keep the existing financial tax_enabled setting as a capability switch,
-- but make seller_gst_registered the statutory gate for checkout tax.
create or replace function public.get_canonical_pricing_config()
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  select jsonb_build_object(
    'tax_enabled',
      (
        coalesce(
          (select value::boolean from public.system_settings where key = 'tax_enabled' limit 1),
          true
        )
        and coalesce(
          (select value::boolean from public.system_settings where key = 'seller_gst_registered' limit 1),
          false
        )
      ),
    'shipping_enabled', coalesce((select value::boolean from public.system_settings where key = 'shipping_enabled' limit 1), true),
    'currency', coalesce((select trim(both '"' from value::text) from public.system_settings where key = 'currency' limit 1), 'INR'),
    'shipping_flat', coalesce((select value::numeric from public.system_settings where key = 'flat_shipping_rate' limit 1), 0),
    'shipping_threshold', coalesce((select value::numeric from public.system_settings where key = 'free_shipping_threshold' limit 1), 0)
  );
$$;

revoke all on function public.get_canonical_pricing_config() from public;
grant execute on function public.get_canonical_pricing_config() to service_role;

commit;
