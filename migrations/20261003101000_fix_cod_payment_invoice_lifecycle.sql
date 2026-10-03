begin;

-- COD can be collected after the order has entered processing.
-- The payment settlement remains the authoritative transition to paid.
create or replace function public.settle_cod_payment(p_order_id uuid, p_user_id uuid)
returns text
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
declare
  v_order public.orders%rowtype;
  v_payment public.payments%rowtype;
  v_payment_id uuid;
  v_provider_payment_id text;
  v_currency text;
  v_existing_status text;
begin
  select * into v_order from public.orders
   where id = p_order_id and customer_id = p_user_id for update;

  if not found then return 'ORDER_NOT_FOUND'; end if;
  if v_order.status not in ('pending', 'processing', 'paid') then return 'INVALID_ORDER_STATE'; end if;

  if v_order.payment_provider is not null
     and lower(trim(v_order.payment_provider)) not in ('', 'cod') then
    return 'PAYMENT_PROVIDER_MISMATCH';
  end if;

  select * into v_payment from public.payments where order_id = p_order_id for update;

  if found then
    v_existing_status := lower(coalesce(v_payment.status, ''));
    if v_payment.payment_provider is not null
       and lower(trim(v_payment.payment_provider)) not in ('', 'cod') then
      return 'PAYMENT_PROVIDER_MISMATCH';
    end if;
    if v_payment.stripe_payment_intent_id is not null then return 'STRIPE_PAYMENT_EXISTS'; end if;
  end if;

  v_provider_payment_id := 'cod:' || p_order_id::text;
  v_currency := upper(coalesce(nullif(trim(v_order.currency), ''), 'INR'));

  if found then
    update public.payments
       set amount = v_order.total_amount,
           amount_paise = round(v_order.total_amount * 100)::bigint,
           currency = v_currency,
           status = 'succeeded',
           payment_method = 'cod',
           payment_provider = 'cod',
           provider_payment_id = v_provider_payment_id,
           successful_attempt_number = coalesce(successful_attempt_number, latest_attempt_number, attempt_number, 1),
           last_attempt_at = coalesce(last_attempt_at, now()),
           updated_at = now()
     where id = v_payment.id
     returning id into v_payment_id;
  else
    insert into public.payments (
      order_id, user_id, stripe_payment_intent_id, payment_provider, provider_payment_id,
      amount, amount_paise, currency, status, payment_method,
      successful_attempt_number, total_attempts, latest_attempt_number, created_at, updated_at
    )
    values (
      p_order_id, p_user_id, null, 'cod', v_provider_payment_id,
      v_order.total_amount, round(v_order.total_amount * 100)::bigint, v_currency, 'succeeded', 'cod',
      1, 1, 1, now(), now()
    )
    returning id into v_payment_id;
  end if;

  insert into public.payment_ledger (
    order_id, payment_id, provider, provider_payment_id, entry_type, direction,
    amount, amount_paise, currency, attempt_number, reference, metadata
  )
  values (
    p_order_id, v_payment_id, 'cod', v_provider_payment_id, 'payment_received', 'credit',
    v_order.total_amount, round(v_order.total_amount * 100)::bigint, v_currency, 1, p_order_id::text,
    jsonb_build_object('source', 'admin_cod_collection', 'payment_method', 'cod')
  )
  on conflict (provider, provider_payment_id, entry_type) do nothing;

  update public.orders
     set status = 'paid',
         payment_provider = 'cod',
         provider_payment_id = v_provider_payment_id,
         stripe_payment_intent = null,
         paid_at = coalesce(paid_at, now()),
         updated_at = now()
   where id = p_order_id;

  if v_existing_status = 'succeeded' then return 'ALREADY_SETTLED'; end if;
  return 'SETTLED';
end;
$function$;

-- Enforce: COD pending -> processing -> paid -> shipped.
create or replace function public.rpc_admin_update_order_status(
  p_order_id uuid,
  p_new_status text,
  p_tracking_number text default null,
  p_notes text default null
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, public
as $function$
declare
  v_order jsonb;
  v_current_status text;
  v_customer_id uuid;
  v_order_payment_method text;
  v_payment_method text;
  v_payment_status text;
  v_provider_payment_id text;
  v_settlement text;
begin
  select status, customer_id, lower(trim(payment_method))
    into v_current_status, v_customer_id, v_order_payment_method
    from public.orders where id = p_order_id for update;

  if not found then return null; end if;

  if lower(p_new_status) = 'paid' then
    select lower(trim(payment_method)), lower(trim(status)), provider_payment_id
      into v_payment_method, v_payment_status, v_provider_payment_id
      from public.payments where order_id = p_order_id for update;

    if coalesce(v_order_payment_method, v_payment_method) = 'cod' then
      v_settlement := public.settle_cod_payment(p_order_id, v_customer_id);
      if v_settlement not in ('SETTLED', 'ALREADY_SETTLED') then
        raise exception 'COD payment settlement failed: %', v_settlement;
      end if;
    elsif lower(coalesce(v_current_status, '')) <> 'paid' then
      raise exception 'PAID status requires provider payment settlement; direct status mutation is not allowed.';
    end if;
  end if;

  if lower(p_new_status) = 'shipped'
     and lower(coalesce(v_current_status, '')) = 'processing'
     and coalesce(v_order_payment_method, v_payment_method) = 'cod' then
    select lower(trim(status)), provider_payment_id
      into v_payment_status, v_provider_payment_id
      from public.payments where order_id = p_order_id for update;

    if coalesce(v_payment_status, '') <> 'succeeded'
       or coalesce(v_provider_payment_id, '') = '' then
      raise exception 'COD order must be paid before shipping.';
    end if;
  end if;

  update public.orders
     set status = p_new_status,
         tracking_number = coalesce(p_tracking_number, tracking_number),
         notes = case when p_notes is not null then coalesce(notes, '') || ' | ' || p_notes else notes end,
         updated_at = now(),
         refunded_at = case when p_new_status = 'refunded' then now() else refunded_at end,
         shipped_at = case when p_new_status = 'shipped' then now() else shipped_at end,
         delivered_at = case when p_new_status = 'delivered' then now() else delivered_at end,
         cancelled_at = case when p_new_status = 'cancelled' then now() else cancelled_at end,
         fulfilled_at = case when p_new_status = 'processing' then now() else fulfilled_at end
   where id = p_order_id
   returning to_jsonb(orders.*) into v_order;

  return v_order;
end;
$function$;

commit;