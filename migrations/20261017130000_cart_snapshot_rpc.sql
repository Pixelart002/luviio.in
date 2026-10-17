begin;

-- Collapse cart + item/product projection + canonical pricing config into one
-- PostgREST RPC round trip. Business pricing remains in CartService/PricingEngine.
create or replace function public.get_cart_snapshot(p_user_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = public, pg_catalog, pg_temp
as $function$
declare
  v_cart_id uuid;
  v_items jsonb;
  v_pricing_config jsonb;
begin
  select c.id
    into v_cart_id
    from public.carts as c
   where c.user_id = p_user_id
   limit 1;

  -- Preserve get-or-create semantics while keeping the normal read path read-only.
  if v_cart_id is null then
    begin
      insert into public.carts (user_id)
      values (p_user_id)
      returning id into v_cart_id;
    exception
      when unique_violation then
        -- Another request may have created the one-cart-per-user row concurrently.
        select c.id
          into v_cart_id
          from public.carts as c
         where c.user_id = p_user_id
         limit 1;
    end;
  end if;

  if v_cart_id is null then
    raise exception 'Unable to resolve cart for user';
  end if;

  select coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', ci.id,
        'product_id', ci.product_id,
        'quantity', ci.quantity,
        'price_snapshot', ci.price_snapshot,
        'added_at', ci.added_at,
        'products',
          case when p.id is null then null else jsonb_build_object(
            'id', p.id,
            'name', p.name,
            'slug', p.slug,
            'price', p.price,
            'compare_price', p.compare_price,
            'stock', p.stock,
            'hsn_code', p.hsn_code,
            'gst_percentage', p.gst_percentage,
            'image_url', p.image_url,
            'is_active', p.is_active,
            'weight', p.weight,
            'weight_unit', p.weight_unit
          ) end
      )
      order by ci.added_at asc
    ),
    '[]'::jsonb
  )
    into v_items
    from public.cart_items as ci
    left join public.products as p on p.id = ci.product_id
   where ci.cart_id = v_cart_id;

  -- Use the existing canonical settings function; no second HTTP/PostgREST call.
  v_pricing_config := public.get_canonical_pricing_config();

  return jsonb_build_object(
    'cart', jsonb_build_object('id', v_cart_id),
    'pricing_config', v_pricing_config,
    'items', coalesce(v_items, '[]'::jsonb)
  );
end;
$function$;

revoke all on function public.get_cart_snapshot(uuid) from public, anon, authenticated;
grant execute on function public.get_cart_snapshot(uuid) to service_role;

commit;
