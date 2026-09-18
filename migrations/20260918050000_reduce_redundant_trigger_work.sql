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
  v_sku text;
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

  select stock, sku
    into v_previous, v_sku
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


-- 2) Make order GST aggregation statement-level.
-- Previously every order_items row caused a full SUM + UPDATE of the parent order.
-- Transition tables let a multi-row insert/update/delete recompute affected orders
-- once per statement instead of once per row.
create or replace function public.sync_order_gst_split_from_items()
returns trigger
language plpgsql
set search_path = public, pg_catalog
as $function$
begin
  update public.orders o
  set
    cgst_amount = x.cgst,
    sgst_amount = x.sgst,
    igst_amount = x.igst
  from (
    select affected.order_id,
           coalesce(sum(oi.cgst_amount), 0) as cgst,
           coalesce(sum(oi.sgst_amount), 0) as sgst,
           coalesce(sum(oi.igst_amount), 0) as igst
    from (
      select order_id from new_rows where order_id is not null
      union
      select order_id from old_rows where order_id is not null
    ) affected
    left join public.order_items oi
      on oi.order_id = affected.order_id
    group by affected.order_id
  ) x
  where o.id = x.order_id
    and (
      o.cgst_amount is distinct from x.cgst
      or o.sgst_amount is distinct from x.sgst
      or o.igst_amount is distinct from x.igst
    );

  return null;
end;
$function$;

drop trigger if exists trg_sync_order_gst_split_from_items on public.order_items;

create trigger trg_sync_order_gst_split_from_items
after insert or update or delete
on public.order_items
referencing old table as old_rows new table as new_rows
for each statement
execute function public.sync_order_gst_split_from_items();


-- 3) Trigger only when the fields its function actually consumes change.
-- This avoids invoking the payment-attempt logging trigger for unrelated payment
-- metadata/updated_at changes.
drop trigger if exists trg_log_payment_attempt on public.payments;

create trigger trg_log_payment_attempt
after insert or update of status
on public.payments
for each row
execute function public.fn_log_payment_attempt();


-- 4) invoice-number formatting only depends on invoice_number/status.
-- Avoid invoking the function for unrelated order updates.
drop trigger if exists trg_auto_format_gst_invoice on public.orders;

create trigger trg_auto_format_gst_invoice
before insert or update of invoice_number, status
on public.orders
for each row
execute function public.auto_format_gst_invoice();

commit;
