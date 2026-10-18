begin;

-- Checkout RPC hot-path reduction:
-- 1) The stock UPDATE already takes the row lock; remove the preceding
--    SELECT ... FOR UPDATE round-trip.
-- 2) cart_items DELETE has a statement-level trigger that updates carts.updated_at;
--    remove the duplicate parent UPDATE.
create or replace function public.create_pending_order_with_payment(
  p_order_data jsonb,
  p_items jsonb,
  p_ip_address text default null,
  p_user_agent text default null
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $function$
declare
  v_order_id uuid;
  v_result jsonb;
  v_item jsonb;
  v_prod_id uuid;
  v_qty int;
  v_merged_item jsonb;
  v_total_amount numeric;
  v_amount_paise bigint;
  v_currency text;
  v_customer_id uuid;
  v_provider text;
  v_provider_payment_id text;
begin
  if jsonb_typeof(p_order_data) <> 'object'
     or jsonb_typeof(p_items) <> 'array'
     or jsonb_array_length(p_items) = 0 then
    raise exception 'PAYMENT_LEDGER_DATA_INVALID';
  end if;

  v_provider := lower(nullif(trim(p_order_data->>'payment_provider'), ''));
  v_provider_payment_id := nullif(trim(p_order_data->>'provider_payment_id'), '');
  v_customer_id := (p_order_data->>'customer_id')::uuid;
  v_total_amount := (p_order_data->>'total_amount')::numeric;
  v_amount_paise := round(v_total_amount * 100)::bigint;
  v_currency := upper(coalesce(nullif(trim(p_order_data->>'currency'), ''), 'INR'));

  if v_customer_id is null
     or v_provider is null
     or v_provider_payment_id is null
     or v_total_amount is null
     or v_total_amount <= 0
     or v_amount_paise <= 0
     or v_currency <> 'INR' then
    raise exception 'PAYMENT_LEDGER_DATA_INVALID';
  end if;

  for v_item in select * from jsonb_array_elements(p_items)
  loop
    begin
      v_prod_id := (v_item->>'product_id')::uuid;
      v_qty := (v_item->>'quantity')::int;
    exception when invalid_text_representation then
      raise exception 'PAYMENT_LEDGER_DATA_INVALID';
    end;

    if v_prod_id is null or v_qty is null or v_qty <= 0 or v_qty > 100 then
      raise exception 'PAYMENT_LEDGER_DATA_INVALID';
    end if;

    update public.products
       set stock = stock - v_qty
     where id = v_prod_id
       and stock >= v_qty;

    if not found then
      raise exception 'Inventory depleted for product_id: %', v_prod_id;
    end if;
  end loop;

  v_order_id := gen_random_uuid();

  -- Explicitly normalize reverse_charge before jsonb_populate_record().
  -- This handles both an omitted key and a JSON null without relying on the
  -- SQL column DEFAULT, which does not apply to explicit NULL values.
  p_order_data := p_order_data || jsonb_build_object(
    'id', v_order_id,
    'tax_type', coalesce(p_order_data->>'tax_type', 'IGST'),
    'reverse_charge', case
      when jsonb_typeof(p_order_data->'reverse_charge') = 'boolean'
        then (p_order_data->>'reverse_charge')::boolean
      else false
    end,
    'created_at', coalesce(p_order_data->>'created_at', now()::text),
    'updated_at', now()::text
  );

  insert into public.orders
  select * from jsonb_populate_record(null::public.orders, p_order_data);

  insert into public.payments (
    order_id,
    user_id,
    stripe_payment_intent_id,
    payment_provider,
    provider_payment_id,
    amount,
    amount_paise,
    currency,
    status,
    attempt_number,
    total_attempts,
    latest_attempt_number,
    successful_attempt_number,
    latest_payment_intent_id,
    max_attempts,
    ip_address,
    user_agent,
    created_at,
    updated_at
  ) values (
    v_order_id,
    v_customer_id,
    case when v_provider = 'stripe' then v_provider_payment_id else null end,
    v_provider,
    v_provider_payment_id,
    v_total_amount,
    v_amount_paise,
    v_currency,
    'requires_payment_method',
    null,
    0,
    null,
    null,
    case when v_provider = 'stripe' then v_provider_payment_id else null end,
    5,
    nullif(trim(p_ip_address), ''),
    nullif(trim(p_user_agent), ''),
    now(),
    now()
  );

  for v_item in select * from jsonb_array_elements(p_items)
  loop
    v_merged_item := v_item || jsonb_build_object(
      'id', gen_random_uuid(),
      'order_id', v_order_id,
      'created_at', now()::text
    );

    insert into public.order_items
    select * from jsonb_populate_record(null::public.order_items, v_merged_item);
  end loop;

  delete from public.cart_items
   where cart_id in (select id from public.carts where user_id = v_customer_id);

  select row_to_json(o)::jsonb
    into v_result
    from public.orders o
   where o.id = v_order_id;

  return v_result;
end;
$function$;

revoke execute on function public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  from public, anon, authenticated;
grant execute on function public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  to service_role;

notify pgrst, 'reload schema';
commit;


notify pgrst, 'reload schema';
commit;
