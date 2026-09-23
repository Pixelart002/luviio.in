-- Stripe publishable key is browser-safe configuration, not a secret.
-- Store it separately from server-only Stripe credentials so the admin console can
-- manage the active public key without ever exposing STRIPE_SECRET_KEY.

insert into public.system_settings
  (key, category, data_type, value, default_value, description, is_system_locked, is_public)
values
  ('stripe_publishable_key', 'financial', 'string', '""'::jsonb, '""'::jsonb,
   'Stripe browser publishable key. Safe to expose to the storefront; never store Stripe secret keys here.',
   false, true)
on conflict (key) do update
set is_public = true,
    description = excluded.description;
