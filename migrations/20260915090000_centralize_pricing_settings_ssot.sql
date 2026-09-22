-- Canonical pricing settings live in system_settings.
-- pricing_config remains a compatibility projection for existing pricing repositories.

insert into public.system_settings (key, category, data_type, value, default_value, description, is_system_locked, is_public)
values
  ('shipping_enabled', 'financial', 'boolean', 'true'::jsonb, 'true'::jsonb, 'Enable storefront shipping charges', false, true),
  ('currency', 'financial', 'string', '"INR"'::jsonb, '"INR"'::jsonb, 'Storefront currency code', true, true)
on conflict (key) do nothing;

create or replace function public.get_canonical_pricing_config()
returns jsonb
language sql
security invoker
stable
set search_path = public
as $$
  select jsonb_build_object(
    'tax_enabled', coalesce((select value from public.system_settings where key = 'tax_enabled'), 'true'::jsonb),
    'shipping_enabled', coalesce((select value from public.system_settings where key = 'shipping_enabled'), 'true'::jsonb),
    'currency', coalesce((select value from public.system_settings where key = 'currency'), '"INR"'::jsonb),
    'shipping_flat', coalesce((select value from public.system_settings where key = 'flat_shipping_rate'), '0'::jsonb),
    'shipping_threshold', coalesce((select value from public.system_settings where key = 'free_shipping_threshold'), '0'::jsonb)
  );
$$;

revoke execute on function public.get_canonical_pricing_config() from public, anon, authenticated;
grant execute on function public.get_canonical_pricing_config() to service_role;

create or replace function public.sync_pricing_config_from_system_settings()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.pricing_config
  set tax_enabled = coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'tax_enabled'), true),
      shipping_enabled = coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'shipping_enabled'), true),
      shipping_flat = coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'flat_shipping_rate'), 0),
      shipping_threshold = coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'free_shipping_threshold'), 0),
      currency = coalesce((select value #>> '{}' from public.system_settings where key = 'currency'), 'INR'),
      updated_at = now();
  return new;
end;
$$;

update public.pricing_config
set tax_enabled = coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'tax_enabled'), true),
    shipping_enabled = coalesce((select (value #>> '{}')::boolean from public.system_settings where key = 'shipping_enabled'), true),
    shipping_flat = coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'flat_shipping_rate'), 0),
    shipping_threshold = coalesce((select (value #>> '{}')::numeric from public.system_settings where key = 'free_shipping_threshold'), 0),
    currency = coalesce((select value #>> '{}' from public.system_settings where key = 'currency'), 'INR'),
    updated_at = now();

drop trigger if exists trg_sync_pricing_config_from_system_settings on public.system_settings;
create trigger trg_sync_pricing_config_from_system_settings
after insert or update of value on public.system_settings
for each row
when (new.key in ('tax_enabled','shipping_enabled','flat_shipping_rate','free_shipping_threshold','currency'))
execute function public.sync_pricing_config_from_system_settings();

revoke execute on function public.sync_pricing_config_from_system_settings() from public, anon, authenticated;
