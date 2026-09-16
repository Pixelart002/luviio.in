begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('business-assets','business-assets',true,5242880,array['image/png','image/jpeg','image/webp'])
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

insert into public.system_settings (
  key, category, data_type, value, default_value, description, is_system_locked, is_public
)
values (
  'business_signature_url', 'general', 'string', '""'::jsonb, '""'::jsonb,
  'Public storage URL for the saved authorised-signatory signature image used on issued business documents.',
  false, false
)
on conflict (key) do nothing;

commit;
