-- Normalize the runtime settings contract around system_settings.
-- Canonical financial keys are the only global checkout configuration:
-- tax_enabled, shipping_enabled, currency, flat_shipping_rate,
-- free_shipping_threshold.
-- Product GST percentage remains product-owned; there is no global GST rate.

-- Remove obsolete aliases that can create conflicting sources of truth.
delete from public.system_settings
where key in (
  'tax_rate',
  'default_tax_rate_percentage',
  'shipping_flat',
  'shipping_threshold',
  'standard_shipping_cost'
);

-- Normalize the canonical keys and their metadata/defaults.
insert into public.system_settings (
  key, category, data_type, value, default_value, description,
  is_system_locked, is_public
)
values
  (
    'tax_enabled', 'financial', 'boolean',
    'true'::jsonb, 'true'::jsonb,
    'Enable product-level GST calculation at checkout. GST percentage is sourced from each product.',
    true, true
  ),
  (
    'shipping_enabled', 'financial', 'boolean',
    'true'::jsonb, 'true'::jsonb,
    'Enable storefront shipping charges.',
    false, true
  ),
  (
    'currency', 'financial', 'string',
    '"INR"'::jsonb, '"INR"'::jsonb,
    'Storefront currency code.',
    true, true
  ),
  (
    'flat_shipping_rate', 'financial', 'decimal',
    '45.90'::jsonb, '45.90'::jsonb,
    'Canonical flat shipping charge in storefront currency.',
    false, true
  ),
  (
    'free_shipping_threshold', 'financial', 'decimal',
    '1499.00'::jsonb, '1499.00'::jsonb,
    'Order subtotal threshold at or above which standard shipping is free.',
    false, true
  )
on conflict (key) do update
set category = excluded.category,
    data_type = excluded.data_type,
    value = excluded.value,
    default_value = excluded.default_value,
    description = excluded.description,
    is_system_locked = excluded.is_system_locked,
    is_public = excluded.is_public;

-- Enforce the canonical values after the upsert even if an earlier migration
-- created the rows with stale metadata.
update public.system_settings
set value = case key
      when 'tax_enabled' then 'true'::jsonb
      when 'shipping_enabled' then 'true'::jsonb
      when 'currency' then '"INR"'::jsonb
      when 'flat_shipping_rate' then '45.90'::jsonb
      when 'free_shipping_threshold' then '1499.00'::jsonb
    end,
    default_value = case key
      when 'tax_enabled' then 'true'::jsonb
      when 'shipping_enabled' then 'true'::jsonb
      when 'currency' then '"INR"'::jsonb
      when 'flat_shipping_rate' then '45.90'::jsonb
      when 'free_shipping_threshold' then '1499.00'::jsonb
    end
where key in (
  'tax_enabled',
  'shipping_enabled',
  'currency',
  'flat_shipping_rate',
  'free_shipping_threshold'
);
