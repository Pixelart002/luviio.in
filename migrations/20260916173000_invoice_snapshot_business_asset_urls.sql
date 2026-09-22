begin;

-- Extend the existing immutable seller snapshot with asset URLs captured
-- from the Business Profile at invoice issuance time. Existing invoices are
-- intentionally untouched.
do $$
declare
  fn text;
  old text := '  return v_invoice_id;';
  new text := $patch$
  update public.invoices set seller_snapshot = seller_snapshot || jsonb_strip_nulls(jsonb_build_object(
    'logo_url', (select nullif(value #>> '{}','') from public.system_settings where key = 'business_logo_url'),
    'signature_url', (select nullif(value #>> '{}','') from public.system_settings where key = 'business_signature_url')
  )) where id = v_invoice_id;

  return v_invoice_id;
$patch$;
begin
  select pg_get_functiondef(p.oid) into fn
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='public' and p.proname='create_invoice_snapshot_for_order';
  if position('signature_url' in fn) > 0 then return; end if;
  fn := replace(fn, old, new);
  execute fn;
end $$;

update public.system_settings
set category='general', is_system_locked=false,
    description='Seller GST state/UT code used for GST place-of-supply classification. Configure from the Business Profile.'
where key='seller_state_code';

commit;
