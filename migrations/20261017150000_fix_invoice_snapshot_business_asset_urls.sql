-- Preserve the live invoice snapshot function and add Business Profile assets.
-- The deployed function currently omits logo/signature URLs even though PDF rendering
-- consumes them from seller_snapshot. Patch only three unique source anchors so all live
-- GST, shipping-tax allocation, shipping-line and compare/MRP logic remains unchanged.
-- Existing immutable invoice rows are intentionally not updated.

BEGIN;

DO $fix$
DECLARE
  function_definition text;
  patched_definition text;

  declaration_anchor constant text := $decl$  v_seller_website text;$decl$;
  declaration_replacement constant text := $decl$  v_seller_website text;
  v_logo_url text;
  v_signature_url text;$decl$;

  setting_read_anchor constant text := $read$  select coalesce(value #>> '{}','') into v_seller_website from public.system_settings where key = 'business_website';$read$;
  setting_read_replacement constant text := $read$  select coalesce(value #>> '{}','') into v_seller_website from public.system_settings where key = 'business_website';
  select coalesce(value #>> '{}','') into v_logo_url from public.system_settings where key = 'business_logo_url';
  select coalesce(value #>> '{}','') into v_signature_url from public.system_settings where key = 'business_signature_url';$read$;

  snapshot_anchor constant text := $snapshot$      'gstin',nullif(v_seller_gstin,''),'gst_registered',v_gstin_registered,'email',nullif(v_seller_email,''),'website',nullif(v_seller_website,''),
      'authorised_signatory_name',nullif(v_signatory_name,''),'authorised_signatory_designation',nullif(v_signatory_designation,'')$snapshot$;
  snapshot_replacement constant text := $snapshot$      'gstin',nullif(v_seller_gstin,''),'gst_registered',v_gstin_registered,'email',nullif(v_seller_email,''),'website',nullif(v_seller_website,''),
      'logo_url',nullif(v_logo_url,''),'signature_url',nullif(v_signature_url,''),
      'authorised_signatory_name',nullif(v_signatory_name,''),'authorised_signatory_designation',nullif(v_signatory_designation,'')$snapshot$;
BEGIN
  SELECT pg_get_functiondef(p.oid)
    INTO function_definition
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname = 'public'
    AND p.proname = 'create_invoice_snapshot_for_order'
    AND pg_get_function_identity_arguments(p.oid) = 'p_order_id uuid';

  IF function_definition IS NULL THEN
    RAISE EXCEPTION 'Cannot repair invoice snapshot: function public.create_invoice_snapshot_for_order(uuid) was not found.';
  END IF;

  IF position('v_logo_url text;' IN function_definition) > 0
     AND position('v_signature_url text;' IN function_definition) > 0
     AND position($logo$'logo_url',nullif(v_logo_url,'')$logo$ IN function_definition) > 0
     AND position($signature$'signature_url',nullif(v_signature_url,'')$signature$ IN function_definition) > 0 THEN
    RAISE NOTICE 'Invoice snapshot function already captures business logo and signature; no change needed.';
    RETURN;
  END IF;

  IF length(function_definition) - length(replace(function_definition, declaration_anchor, '')) <> length(declaration_anchor) THEN
    RAISE EXCEPTION 'Invoice snapshot declaration anchor was not unique; refusing to overwrite function.';
  END IF;
  IF length(function_definition) - length(replace(function_definition, setting_read_anchor, '')) <> length(setting_read_anchor) THEN
    RAISE EXCEPTION 'Invoice snapshot settings-read anchor was not unique; refusing to overwrite function.';
  END IF;
  IF length(function_definition) - length(replace(function_definition, snapshot_anchor, '')) <> length(snapshot_anchor) THEN
    RAISE EXCEPTION 'Invoice snapshot JSON anchor was not unique; refusing to overwrite function.';
  END IF;

  patched_definition := replace(function_definition, declaration_anchor, declaration_replacement);
  patched_definition := replace(patched_definition, setting_read_anchor, setting_read_replacement);
  patched_definition := replace(patched_definition, snapshot_anchor, snapshot_replacement);

  IF position('v_logo_url text;' IN patched_definition) = 0
     OR position('v_signature_url text;' IN patched_definition) = 0
     OR position($logo$'logo_url',nullif(v_logo_url,'')$logo$ IN patched_definition) = 0
     OR position($signature$'signature_url',nullif(v_signature_url,'')$signature$ IN patched_definition) = 0 THEN
    RAISE EXCEPTION 'Invoice snapshot asset patch did not produce the expected function definition.';
  END IF;

  EXECUTE patched_definition;
END;
$fix$;

COMMIT;
