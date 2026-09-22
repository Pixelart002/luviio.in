begin;

create or replace function public.normalize_gst_state_code(p_state text)
returns text
language plpgsql
immutable
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v text := lower(trim(coalesce(p_state, '')));
begin
  if v = '' then return null; end if;

  if v in ('ap','andhra pradesh') then return 'AP'; end if;
  if v in ('ar','arunachal pradesh') then return 'AR'; end if;
  if v in ('as','assam') then return 'AS'; end if;
  if v in ('br','bihar') then return 'BR'; end if;
  if v in ('cg','ct','chhattisgarh') then return 'CG'; end if;
  if v in ('ga','goa') then return 'GA'; end if;
  if v in ('gj','gujarat') then return 'GJ'; end if;
  if v in ('hr','haryana') then return 'HR'; end if;
  if v in ('hp','himachal pradesh') then return 'HP'; end if;
  if v in ('jh','jharkhand') then return 'JH'; end if;
  if v in ('ka','karnataka') then return 'KA'; end if;
  if v in ('kl','kerala') then return 'KL'; end if;
  if v in ('mp','madhya pradesh') then return 'MP'; end if;
  if v in ('mh','maharashtra') then return 'MH'; end if;
  if v in ('mn','manipur') then return 'MN'; end if;
  if v in ('ml','meghalaya') then return 'ML'; end if;
  if v in ('mz','mizoram') then return 'MZ'; end if;
  if v in ('nl','nagaland') then return 'NL'; end if;
  if v in ('od','or','odisha') then return 'OD'; end if;
  if v in ('pb','punjab') then return 'PB'; end if;
  if v in ('rj','rajasthan') then return 'RJ'; end if;
  if v in ('sk','sikkim') then return 'SK'; end if;
  if v in ('tn','tamil nadu') then return 'TN'; end if;
  if v in ('ts','tg','telangana') then return 'TS'; end if;
  if v in ('tr','tripura') then return 'TR'; end if;
  if v in ('up','uttar pradesh') then return 'UP'; end if;
  if v in ('uk','ut','uttarakhand') then return 'UK'; end if;
  if v in ('wb','west bengal') then return 'WB'; end if;
  if v in ('an','andaman and nicobar islands') then return 'AN'; end if;
  if v in ('ch','chandigarh') then return 'CH'; end if;
  if v in ('dh','dn','dadra and nagar haveli and daman and diu') then return 'DH'; end if;
  if v in ('dl','delhi','new delhi') then return 'DL'; end if;
  if v in ('jk','jammu and kashmir') then return 'JK'; end if;
  if v in ('la','ladakh') then return 'LA'; end if;
  if v in ('ld','lakshadweep') then return 'LD'; end if;
  if v in ('py','puducherry') then return 'PY'; end if;

  if position('andhra pradesh' in v) > 0 then return 'AP'; end if;
  if position('arunachal pradesh' in v) > 0 then return 'AR'; end if;
  if position('assam' in v) > 0 then return 'AS'; end if;
  if position('bihar' in v) > 0 then return 'BR'; end if;
  if position('chhattisgarh' in v) > 0 then return 'CG'; end if;
  if position('goa' in v) > 0 then return 'GA'; end if;
  if position('gujarat' in v) > 0 then return 'GJ'; end if;
  if position('haryana' in v) > 0 then return 'HR'; end if;
  if position('himachal pradesh' in v) > 0 then return 'HP'; end if;
  if position('jharkhand' in v) > 0 then return 'JH'; end if;
  if position('karnataka' in v) > 0 or position('bengaluru' in v) > 0 then return 'KA'; end if;
  if position('kerala' in v) > 0 then return 'KL'; end if;
  if position('madhya pradesh' in v) > 0 then return 'MP'; end if;
  if position('maharashtra' in v) > 0 or position('mumbai' in v) > 0 then return 'MH'; end if;
  if position('manipur' in v) > 0 then return 'MN'; end if;
  if position('meghalaya' in v) > 0 then return 'ML'; end if;
  if position('mizoram' in v) > 0 then return 'MZ'; end if;
  if position('nagaland' in v) > 0 then return 'NL'; end if;
  if position('odisha' in v) > 0 then return 'OD'; end if;
  if position('punjab' in v) > 0 then return 'PB'; end if;
  if position('rajasthan' in v) > 0 then return 'RJ'; end if;
  if position('sikkim' in v) > 0 then return 'SK'; end if;
  if position('tamil nadu' in v) > 0 or position('chennai' in v) > 0 then return 'TN'; end if;
  if position('telangana' in v) > 0 or position('hyderabad' in v) > 0 then return 'TS'; end if;
  if position('tripura' in v) > 0 then return 'TR'; end if;
  if position('uttar pradesh' in v) > 0 then return 'UP'; end if;
  if position('uttarakhand' in v) > 0 then return 'UK'; end if;
  if position('west bengal' in v) > 0 or position('kolkata' in v) > 0 then return 'WB'; end if;
  if position('andaman and nicobar' in v) > 0 then return 'AN'; end if;
  if position('chandigarh' in v) > 0 then return 'CH'; end if;
  if position('dadra and nagar haveli' in v) > 0 or position('daman and diu' in v) > 0 then return 'DH'; end if;
  if position('delhi' in v) > 0 or position('new delhi' in v) > 0 then return 'DL'; end if;
  if position('jammu and kashmir' in v) > 0 then return 'JK'; end if;
  if position('ladakh' in v) > 0 then return 'LA'; end if;
  if position('lakshadweep' in v) > 0 then return 'LD'; end if;
  if position('puducherry' in v) > 0 then return 'PY'; end if;

  return upper(left(v, 2));
end;
$$;

update public.orders o
set seller_state_code = public.normalize_gst_state_code(coalesce((select value #>> '{}' from public.system_settings where key='seller_state_code' limit 1),'DL')),
    place_of_supply_state_code = public.normalize_gst_state_code(o.shipping_state),
    tax_type = case
      when public.normalize_gst_state_code(o.shipping_state) is not null
       and public.normalize_gst_state_code(o.shipping_state) = public.normalize_gst_state_code(coalesce((select value #>> '{}' from public.system_settings where key='seller_state_code' limit 1),'DL'))
      then 'CGST+SGST'
      else 'IGST'
    end;

update public.order_items oi
set cgst_amount = case when o.tax_type='CGST+SGST' then round(coalesce(oi.tax_amount,0)/2,2) else 0 end,
    sgst_amount = case when o.tax_type='CGST+SGST' then coalesce(oi.tax_amount,0)-round(coalesce(oi.tax_amount,0)/2,2) else 0 end,
    igst_amount = case when o.tax_type='IGST' then coalesce(oi.tax_amount,0) else 0 end
from public.orders o where o.id=oi.order_id;

update public.orders o
set cgst_amount=coalesce(x.cgst,0), sgst_amount=coalesce(x.sgst,0), igst_amount=coalesce(x.igst,0)
from (select order_id,sum(cgst_amount) cgst,sum(sgst_amount) sgst,sum(igst_amount) igst from public.order_items group by order_id) x
where x.order_id=o.id;

commit;
