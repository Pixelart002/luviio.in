begin;

-- 1) Stop admin_adjust_stock from duplicating the stock_audit write.
-- The products.stock trigger already records every real stock transition
-- into stock_audit and inventory_activity. Keep updated_at trigger-owned too.
create or replace function public.admin_adjust_stock(
  p_product_id uuid,
  p_delta integer,
  p_reason text
)
returns table(
  product_id uuid,
  previous_stock integer,
  new_stock integer,
  delta integer,
  reason text
)
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
declare
  v_previous integer;
  v_new integer;
  v_reason text;
begin
  if p_delta = 0 then
    raise exception 'STOCK_ADJUSTMENT_ZERO';
  end if;

  v_reason := nullif(btrim(p_reason), '');
  if v_reason is null then
    raise exception 'STOCK_ADJUSTMENT_REASON_REQUIRED';
  end if;

  if char_length(v_reason) > 500 then
    raise exception 'STOCK_ADJUSTMENT_REASON_TOO_LONG';
  end if;

  select stock
    into v_previous
  from public.products
  where id = p_product_id
  for update;

  if not found then
    raise exception 'PRODUCT_NOT_FOUND';
  end if;

  if v_previous + p_delta < 0 then
    raise exception 'INSUFFICIENT_STOCK';
  end if;

  v_new := v_previous + p_delta;

  -- The stock transition triggers own updated_at/audit/activity/outbox.
  update public.products
     set stock = v_new
   where id = p_product_id;

  return query
    select p_product_id, v_previous, v_new, p_delta, v_reason;
end;
$function$;

revoke all on function public.admin_adjust_stock(uuid, integer, text) from public, anon, authenticated;
grant execute on function public.admin_adjust_stock(uuid, integer, text) to service_role;


-- 2) Common GST refresh helper. The UPDATE is skipped completely when the
-- aggregate values are already equal, preventing unnecessary parent-row writes.
create or replace function public.refresh_order_gst_split(p_order_id uuid)
returns void
language sql
set search_path = public, pg_catalog
as $function$
  with aggregate_values as (
    select
      coalesce(sum(cgst_amount), 0) as cgst,
      coalesce(sum(sgst_amount), 0) as sgst,
      coalesce(sum(igst_amount), 0) as igst
    from public.order_items
    where order_id = p_order_id
  )
  update public.orders o
     set cgst_amount = a.cgst,
         sgst_amount = a.sgst,
         igst_amount = a.igst
    from aggregate_values a
   where o.id = p_order_id
     and (
       o.cgst_amount is distinct from a.cgst
       or o.sgst_amount is distinct from a.sgst
       or o.igst_amount is distinct from a.igst
     );
$function$;


-- Compatibility wrapper for any legacy trigger reference. New production trigger
-- paths below are statement-level and do not invoke this row-level wrapper.
create or replace function public.sync_order_gst_split_from_items()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
begin
  perform public.refresh_order_gst_split(coalesce(new.order_id, old.order_id));
  return coalesce(new, old);
end;
$function$;


create or replace function public.sync_order_gst_split_after_insert()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_order_id uuid;
begin
  for v_order_id in
    select distinct order_id
    from new_rows
    where order_id is not null
  loop
    perform public.refresh_order_gst_split(v_order_id);
  end loop;
  return null;
end;
$function$;


create or replace function public.sync_order_gst_split_after_update()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_order_id uuid;
begin
  for v_order_id in
    select distinct order_id
    from (
      select order_id from new_rows
      union
      select order_id from old_rows
    ) affected
    where order_id is not null
  loop
    perform public.refresh_order_gst_split(v_order_id);
  end loop;
  return null;
end;
$function$;


create or replace function public.sync_order_gst_split_after_delete()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
declare
  v_order_id uuid;
begin
  for v_order_id in
    select distinct order_id
    from old_rows
    where order_id is not null
  loop
    perform public.refresh_order_gst_split(v_order_id);
  end loop;
  return null;
end;
$function$;


drop trigger if exists trg_sync_order_gst_split_from_items on public.order_items;

create trigger trg_sync_order_gst_split_after_insert
after insert
on public.order_items
referencing new table as new_rows
for each statement
execute function public.sync_order_gst_split_after_insert();

create trigger trg_sync_order_gst_split_after_update
after update
on public.order_items
referencing old table as old_rows new table as new_rows
for each statement
execute function public.sync_order_gst_split_after_update();

create trigger trg_sync_order_gst_split_after_delete
after delete
on public.order_items
referencing old table as old_rows
for each statement
execute function public.sync_order_gst_split_after_delete();


-- 3) Trigger only when the fields its function actually consumes change.
drop trigger if exists trg_log_payment_attempt on public.payments;

create trigger trg_log_payment_attempt
after insert or update of status
on public.payments
for each row
execute function public.fn_log_payment_attempt();


-- 4) Invoice-number formatting only depends on invoice_number/status.
drop trigger if exists trg_auto_format_gst_invoice on public.orders;

create trigger trg_auto_format_gst_invoice
before insert or update of invoice_number, status
on public.orders
for each row
execute function public.auto_format_gst_invoice();

commit;
