begin;

-- Luviio uses manual shipping fulfillment. Restore the store-owned shipping
-- configuration removed by the previous external-provider migration so the
-- checkout quote has one canonical source of truth.

insert into public.system_settings (
  key, category, data_type, value, default_value, description,
  is_system_locked, is_public
)
values
  (
    'shipping_enabled',
    'financial',
    'boolean',
    'true'::jsonb,
    'true'::jsonb,
    'Enable storefront shipping charges',
    false,
    true
  ),
  (
    'flat_shipping_rate',
    'financial',
    'number',
    '45.90'::jsonb,
    '45.90'::jsonb,
    'Manual shipping charge below the free-shipping threshold (INR)',
    false,
    true
  ),
  (
    'free_shipping_threshold',
    'financial',
    'number',
    '1499'::jsonb,
    '1499'::jsonb,
    'Order subtotal at or above which manual shipping is free (INR)',
    false,
    true
  )
on conflict (key) do update
set
  value = excluded.value,
  default_value = excluded.default_value,
  description = excluded.description,
  category = excluded.category,
  data_type = excluded.data_type,
  is_system_locked = excluded.is_system_locked,
  is_public = excluded.is_public;

-- Keep the pricing compatibility projection synchronized with the restored
-- canonical system settings.
update public.pricing_config
set
  shipping_enabled = true,
  shipping_flat = 45.90,
  shipping_threshold = 1499,
  updated_at = now();

commit;
