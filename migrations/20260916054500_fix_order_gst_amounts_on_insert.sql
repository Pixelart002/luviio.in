begin;

create or replace function public.set_order_gst_context()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_seller text;
  v_pos text;
  v_tax numeric := coalesce(new.tax_amount, 0);
begin
  select public.normalize_gst_state_code(coalesce(value #>> '{}', 'DL'))
    into v_seller
  from public.system_settings
  where key = 'seller_state_code'
  limit 1;

  v_seller := coalesce(v_seller, 'DL');
  v_pos := public.normalize_gst_state_code(new.shipping_state);

  new.seller_state_code := v_seller;
  new.place_of_supply_state_code := v_pos;
  new.tax_type := case
    when v_pos is not null and v_pos = v_seller then 'CGST+SGST'
    else 'IGST'
  end;

  new.cgst_amount := case when new.tax_type = 'CGST+SGST' then round(v_tax / 2, 2) else 0 end;
  new.sgst_amount := case when new.tax_type = 'CGST+SGST' then v_tax - round(v_tax / 2, 2) else 0 end;
  new.igst_amount := case when new.tax_type = 'IGST' then v_tax else 0 end;

  return new;
end;
$$;

commit;
