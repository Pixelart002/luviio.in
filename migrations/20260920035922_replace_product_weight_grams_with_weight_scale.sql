-- Replace the product weight contract with a value + explicit scale.
-- Existing valid product HSN rows are migrated as grams to preserve the old
-- integer weight meaning. Legacy rows with invalid HSN are intentionally not
-- copied because the existing NOT VALID HSN check rejects updates to them.

alter table public.products
  add column weight numeric(12,3),
  add column weight_unit text;

update public.products
set weight = weight_grams::numeric,
    weight_unit = 'g'
where weight_grams is not null
  and hsn_code ~ '^[0-9]{4,8}$';

alter table public.products
  add constraint products_weight_nonnegative_chk
    check (weight is null or weight >= 0),
  add constraint products_weight_unit_chk
    check (weight_unit is null or weight_unit in ('g','kg'));

alter table public.products
  drop column weight_grams;
