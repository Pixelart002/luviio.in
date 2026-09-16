begin;

-- Minimal business master/profile boundary.
-- Keep operational checkout configuration in system_settings as before;
-- these keys are the canonical seller/business identity used by future
-- document generation and admin profile management. No legal values are
-- fabricated here; empty values intentionally keep the profile incomplete
-- until the owner supplies the real business information.
insert into public.system_settings (
  key, category, data_type, value, default_value, description,
  is_system_locked, is_public
)
values
  ('business_brand_name', 'general', 'string', '"Luviio"'::jsonb, '""'::jsonb,
   'Customer-facing business/brand name.', false, true),
  ('business_legal_name', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Legal seller/business name used on official documents. Must be supplied from real business records.', false, false),
  ('business_type', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Business constitution/type, when applicable (for example proprietorship, partnership, LLP, company).', false, false),
  ('business_email', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Primary business contact email.', false, true),
  ('business_phone', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Primary business contact phone.', false, true),
  ('business_website', 'general', 'string', '"https://luviio.in"'::jsonb, '""'::jsonb,
   'Canonical business website.', false, true),
  ('business_logo_url', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Canonical business logo URL for documents and public brand surfaces.', false, true),
  ('seller_address_line1', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller registered/business address line 1. Required before seller invoice snapshots can be created.', false, false),
  ('seller_address_line2', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller registered/business address line 2, if applicable.', false, false),
  ('seller_city', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller registered/business city.', false, false),
  ('seller_district', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller registered/business district, if applicable.', false, false),
  ('seller_state', 'general', 'string', '"Delhi"'::jsonb, '""'::jsonb,
   'Seller registered/business state name.', false, false),
  ('seller_state_code', 'general', 'string', '"DL"'::jsonb, '""'::jsonb,
   'Seller state/UT code used for GST place-of-supply classification. Existing orders remain authoritative.', false, false),
  ('seller_pincode', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller registered/business postal PIN code.', false, false),
  ('seller_country', 'general', 'string', '"India"'::jsonb, '"India"'::jsonb,
   'Seller country.', false, false),
  ('seller_gst_registered', 'general', 'boolean', 'false'::jsonb, 'false'::jsonb,
   'Whether the seller is actually GST registered. Do not enable without valid registration records.', false, false),
  ('seller_gstin', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller GSTIN. Keep blank when the seller is not GST registered.', false, false),
  ('seller_pan', 'general', 'string', '""'::jsonb, '""'::jsonb,
   'Seller PAN from official business records. Private administrative data.', false, false)
on conflict (key) do nothing;

commit;
