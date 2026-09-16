begin;

-- Canonical seller state for GST place-of-supply classification.
insert into public.system_settings (key, category, data_type, value, default_value, description, is_system_locked, is_public)
values (
  'seller_state_code',
  'financial',
  'string',
  '"DL"'::jsonb,
  '"DL"'::jsonb,
  'Seller GST registration state code used to classify intra-state vs inter-state supply. Configure to the actual registered seller state before statutory invoicing.',
  true,
  false
)
on conflict (key) do update
set description = excluded.description,
    is_system_locked = true,
    is_public = false,
    updated_at = now();

alter table public.orders
  add column if not exists seller_state_code text,
  add column if not exists place_of_supply_state_code text,
  add column if not exists cgst_amount numeric not null default 0,
  add column if not exists sgst_amount numeric not null default 0,
  add column if not exists igst_amount numeric not null default 0;

alter table public.order_items
  add column if not exists cgst_amount numeric not null default 0,
  add column if not exists sgst_amount numeric not null default 0,
  add column if not exists igst_amount numeric not null default 0;

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
  return case v
    when 'andhra pradesh' then 'AP' when 'arunachal pradesh' then 'AR' when 'assam' then 'AS' when 'bihar' then 'BR'
    when 'chhattisgarh' then 'CG' when 'goa' then 'GA' when 'gujarat' then 'GJ' when 'haryana' then 'HR'
    when 'himachal pradesh' then 'HP' when 'jharkhand' then 'JH' when 'karnataka' then 'KA' when 'kerala' then 'KL'
    when 'madhya pradesh' then 'MP' when 'maharashtra' then 'MH' when 'manipur' then 'MN' when 'meghalaya' then 'ML'
    when 'mizoram' then 'MZ' when 'nagaland' then 'NL' when 'odisha' then 'OD' when 'punjab' then 'PB'
    when 'rajasthan' then 'RJ' when 'sikkim' then 'SK' when 'tamil nadu' then 'TN' when 'telangana' then 'TS'
    when 'tripura' then 'TR' when 'uttar pradesh' then 'UP' when 'uttarakhand' then 'UK' when 'west bengal' then 'WB'
    when 'andaman and nicobar islands' then 'AN' when 'chandigarh' then 'CH'
    when 'dadra and nagar haveli and daman and diu' then 'DH' when 'delhi' then 'DL' when 'new delhi' then 'DL'
    when 'jammu and kashmir' then 'JK' when 'ladakh' then 'LA' when 'lakshadweep' then 'LD' when 'puducherry' then 'PY'
    when 'ap' then 'AP' when 'ar' then 'AR' when 'as' then 'AS' when 'br' then 'BR' when 'cg' then 'CG' when 'ct' then 'CG'
    when 'ga' then 'GA' when 'gj' then 'GJ' when 'hr' then 'HR' when 'hp' then 'HP' when 'jh' then 'JH' when 'ka' then 'KA'
    when 'kl' then 'KL' when 'mp' then 'MP' when 'mh' then 'MH' when 'mn' then 'MN' when 'ml' then 'ML' when 'mz' then 'MZ'
    when 'nl' then 'NL' when 'or' then 'OD' when 'od' then 'OD' when 'pb' then 'PB' when 'rj' then 'RJ' when 'sk' then 'SK'
    when 'tn' then 'TN' when 'tg' then 'TS' when 'ts' then 'TS' when 'tr' then 'TR' when 'up' then 'UP' when 'ut' then 'UK'
    when 'uk' then 'UK' when 'wb' then 'WB' when 'an' then 'AN' when 'ch' then 'CH' when 'dh' then 'DH' when 'dn' then 'DH'
    when 'dl' then 'DL' when 'jk' then 'JK' when 'la' then 'LA' when 'ld' then 'LD' when 'py' then 'PY'
    else upper(left(v, 2))
  end;
end;
$$;

create or replace function public.set_order_gst_context()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_seller text;
  v_pos text;
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

  return new;
end;
$$;

drop trigger if exists trg_set_order_gst_context on public.orders;
create trigger trg_set_order_gst_context
before insert or update of shipping_state
on public.orders
for each row execute function public.set_order_gst_context();

-- Backfill line GST tax snapshots without changing existing order totals.
update public.order_items
set tax_amount = round(coalesce(subtotal, unit_price * quantity, 0) * coalesce(gst_percentage, 0) / 100, 2)
where tax_amount is null;

-- Reclassify historical orders using the configured seller state; monetary totals remain untouched.
update public.orders o
set seller_state_code = public.normalize_gst_state_code(
      coalesce((select value #>> '{}' from public.system_settings where key = 'seller_state_code' limit 1), 'DL')
    ),
    place_of_supply_state_code = public.normalize_gst_state_code(o.shipping_state),
    tax_type = case
      when public.normalize_gst_state_code(o.shipping_state) is not null
       and public.normalize_gst_state_code(o.shipping_state) = public.normalize_gst_state_code(
         coalesce((select value #>> '{}' from public.system_settings where key = 'seller_state_code' limit 1), 'DL')
       )
      then 'CGST+SGST'
      else 'IGST'
    end;

-- Materialize historical line-level tax split from the corrected order tax type.
update public.order_items oi
set cgst_amount = case when o.tax_type = 'CGST+SGST' then round(coalesce(oi.tax_amount, 0) / 2, 2) else 0 end,
    sgst_amount = case when o.tax_type = 'CGST+SGST' then coalesce(oi.tax_amount, 0) - round(coalesce(oi.tax_amount, 0) / 2, 2) else 0 end,
    igst_amount = case when o.tax_type = 'IGST' then coalesce(oi.tax_amount, 0) else 0 end
from public.orders o
where o.id = oi.order_id;

-- Materialize order-level GST components without recalculating subtotal/shipping/total.
update public.orders o
set cgst_amount = coalesce(x.cgst, 0),
    sgst_amount = coalesce(x.sgst, 0),
    igst_amount = coalesce(x.igst, 0)
from (
  select order_id,
         sum(cgst_amount) as cgst,
         sum(sgst_amount) as sgst,
         sum(igst_amount) as igst
  from public.order_items
  group by order_id
) x
where x.order_id = o.id;

-- Future order-item rows get authoritative GST snapshots automatically.
create or replace function public.set_order_item_gst_snapshot()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
declare
  v_tax numeric;
  v_tax_type text;
begin
  v_tax := round(
    coalesce(new.subtotal, new.unit_price * new.quantity, 0)
    * coalesce(new.gst_percentage, 0) / 100,
    2
  );
  new.tax_amount := v_tax;

  select tax_type into v_tax_type
  from public.orders
  where id = new.order_id;

  new.cgst_amount := case when v_tax_type = 'CGST+SGST' then round(v_tax / 2, 2) else 0 end;
  new.sgst_amount := case when v_tax_type = 'CGST+SGST' then v_tax - round(v_tax / 2, 2) else 0 end;
  new.igst_amount := case when v_tax_type = 'IGST' then v_tax else 0 end;

  return new;
end;
$$;

drop trigger if exists trg_set_order_item_gst_snapshot on public.order_items;
create trigger trg_set_order_item_gst_snapshot
before insert or update of subtotal, unit_price, quantity, gst_percentage, tax_amount, order_id
on public.order_items
for each row execute function public.set_order_item_gst_snapshot();

-- Keep order-level GST split synchronized with line snapshots. This never changes total_amount.
create or replace function public.sync_order_gst_split_from_items()
returns trigger
language plpgsql
set search_path = public, pg_catalog, pg_temp
as $$
begin
  update public.orders o
  set cgst_amount = coalesce(x.cgst, 0),
      sgst_amount = coalesce(x.sgst, 0),
      igst_amount = coalesce(x.igst, 0)
  from (
    select order_id,
           sum(cgst_amount) as cgst,
           sum(sgst_amount) as sgst,
           sum(igst_amount) as igst
    from public.order_items
    where order_id = coalesce(new.order_id, old.order_id)
    group by order_id
  ) x
  where o.id = x.order_id;

  return coalesce(new, old);
end;
$$;

drop trigger if exists trg_sync_order_gst_split_from_items on public.order_items;
create trigger trg_sync_order_gst_split_from_items
after insert or update or delete
on public.order_items
for each row execute function public.sync_order_gst_split_from_items();

commit;
