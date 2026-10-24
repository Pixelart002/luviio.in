-- Keep the discount components in the immutable invoice totals snapshot.
-- This patches only the live snapshot function; already-issued invoice rows remain untouched.
begin;

do $fix$
declare
  function_definition text;
  patched_definition text;
  totals_anchor constant text := $anchor$'discount_amount',coalesce(v_order.discount_amount,0),'shipping_cost',coalesce(v_order.shipping_cost,0),$anchor$;
  totals_replacement constant text := $replace$'discount_amount',coalesce(v_order.discount_amount,0),'membership_discount_amount',coalesce(v_order.membership_discount_amount,0),'membership_discount_percent',coalesce(v_order.membership_discount_percent,0),'coupon_discount_amount',coalesce(v_order.coupon_discount_amount,0),'shipping_cost',coalesce(v_order.shipping_cost,0),$replace$;
begin
  select pg_get_functiondef(p.oid)
    into function_definition
  from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'create_invoice_snapshot_for_order'
    and pg_get_function_identity_arguments(p.oid) = 'p_order_id uuid';

  if function_definition is null then
    raise exception 'Cannot add invoice discount breakdown: public.create_invoice_snapshot_for_order(uuid) was not found.';
  end if;

  if position($membership$'membership_discount_amount',coalesce(v_order.membership_discount_amount,0)$membership$ in function_definition) > 0
     and position($coupon$'coupon_discount_amount',coalesce(v_order.coupon_discount_amount,0)$coupon$ in function_definition) > 0 then
    raise notice 'Invoice snapshot already captures the discount breakdown; no change needed.';
    return;
  end if;

  if length(function_definition) - length(replace(function_definition, totals_anchor, '')) <> length(totals_anchor) then
    raise exception 'Invoice totals anchor was not unique; refusing to overwrite the snapshot function.';
  end if;

  patched_definition := replace(function_definition, totals_anchor, totals_replacement);

  if position($membership$'membership_discount_amount',coalesce(v_order.membership_discount_amount,0)$membership$ in patched_definition) = 0
     or position($coupon$'coupon_discount_amount',coalesce(v_order.coupon_discount_amount,0)$coupon$ in patched_definition) = 0
     or position($percent$'membership_discount_percent',coalesce(v_order.membership_discount_percent,0)$percent$ in patched_definition) = 0 then
    raise exception 'Invoice discount snapshot patch did not produce the expected function definition.';
  end if;

  execute patched_definition;
end;
$fix$;

commit;
