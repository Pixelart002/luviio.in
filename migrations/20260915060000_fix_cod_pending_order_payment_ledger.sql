-- COD orders do not have a Stripe PaymentIntent. The shared order-creation
-- transaction must therefore allow a NULL payment-intent for COD while still
-- creating an auditable payment ledger row.

create or replace function public.create_pending_order_with_reservation(p_order_data jsonb, p_items jsonb)
returns jsonb
language plpgsql
security definer
set search_path to 'public', 'pg_catalog', 'pg_temp'
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
  v_payment_intent_id text;
  v_payment_method text;
begin
  for v_item in select * from jsonb_array_elements(p_items)
  loop
    v_prod_id := (v_item->>'product_id')::uuid;
    v_qty := (v_item->>'quantity')::int;
    update public.products set stock = stock - v_qty
      where id = v_prod_id and stock >= v_qty;
    if not found then
      raise exception 'Inventory depleted for product_id: %', v_prod_id;
    end if;
  end loop;

  v_order_id := gen_random_uuid();
  p_order_data := p_order_data || jsonb_build_object(
    'id', v_order_id,
    'tax_type', coalesce(p_order_data->>'tax_type', 'IGST'),
    'created_at', coalesce(p_order_data->>'created_at', now()::text),
    'updated_at', now()::text
  );

  insert into public.orders
  select * from jsonb_populate_record(null::public.orders, p_order_data);

  v_customer_id := (p_order_data->>'customer_id')::uuid;
  v_payment_intent_id := nullif(trim(p_order_data->>'stripe_payment_intent'), '');
  v_total_amount := (p_order_data->>'total_amount')::numeric;
  v_amount_paise := round(v_total_amount * 100)::bigint;
  v_currency := upper(coalesce(nullif(trim(p_order_data->>'currency'), ''), 'INR'));
  v_payment_method := lower(coalesce(nullif(trim(p_order_data->>'payment_method'), ''), 'cod'));

  if v_customer_id is null or v_total_amount is null or v_total_amount < 0 then
    raise exception 'PAYMENT_LEDGER_DATA_INVALID';
  end if;

  if v_payment_intent_id is null then
    insert into public.payments (
      order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
      payment_method,attempt_number,total_attempts,latest_attempt_number,successful_attempt_number,
      latest_payment_intent_id,max_attempts,created_at,updated_at
    ) values (
      v_order_id,v_customer_id,null,v_total_amount,v_amount_paise,v_currency,'pending',
      'cod',null,0,null,null,null,5,now(),now()
    );
  else
    insert into public.payments (
      order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
      payment_method,attempt_number,total_attempts,latest_attempt_number,successful_attempt_number,
      latest_payment_intent_id,max_attempts,created_at,updated_at
    ) values (
      v_order_id,v_customer_id,v_payment_intent_id,v_total_amount,v_amount_paise,v_currency,
      'requires_payment_method',v_payment_method,null,0,null,null,v_payment_intent_id,5,now(),now()
    );
  end if;

  for v_item in select * from jsonb_array_elements(p_items)
  loop
    v_merged_item := v_item || jsonb_build_object(
      'id', gen_random_uuid(), 'order_id', v_order_id, 'created_at', now()::text
    );
    insert into public.order_items
    select * from jsonb_populate_record(null::public.order_items, v_merged_item);
  end loop;

  delete from public.cart_items
    where cart_id in (select id from public.carts where user_id = v_customer_id);
  update public.carts set updated_at = now() where user_id = v_customer_id;

  select row_to_json(o)::jsonb into v_result from public.orders o where o.id = v_order_id;
  return v_result;
end;
$function$;

revoke all on function public.create_pending_order_with_reservation(jsonb,jsonb) from public;
grant execute on function public.create_pending_order_with_reservation(jsonb,jsonb) to service_role;
