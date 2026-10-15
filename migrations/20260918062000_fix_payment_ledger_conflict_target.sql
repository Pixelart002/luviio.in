-- Fix payment ledger idempotency targets after refund-ledger split.
-- The payment_received uniqueness is partial, so PostgreSQL requires the
-- matching partial predicate in ON CONFLICT for constraint inference.
create or replace function public.settle_payment_transaction(
    p_order_id uuid,
    p_provider text,
    p_provider_payment_id text,
    p_amount numeric,
    p_user_id uuid,
    p_payment_method text default null,
    p_currency text default null
)
returns text
language plpgsql
security definer
set search_path to 'pg_catalog', 'public'
as $function$
declare
  v_order public.orders%rowtype;
  v_existing public.payments%rowtype;
  v_currency text;
  v_payment_id uuid;
  v_attempt integer;
begin
  p_provider := lower(nullif(trim(p_provider), ''));
  p_provider_payment_id := nullif(trim(p_provider_payment_id), '');
  v_currency := upper(nullif(trim(p_currency), ''));
  if p_provider is null or p_provider_payment_id is null then return 'PAYMENT_IDENTITY_INVALID'; end if;

  select * into v_order from public.orders
   where id = p_order_id and customer_id = p_user_id for update;
  if not found then return 'ORDER_NOT_FOUND'; end if;
  if v_order.status = 'paid' then return 'ALREADY_PAID'; end if;
  if v_order.status = 'cancelled' then return 'ORDER_ALREADY_CANCELLED'; end if;
  if p_amount is null or p_amount <= 0 or round(p_amount,2) <> round(v_order.total_amount,2) then return 'PAYMENT_AMOUNT_MISMATCH'; end if;
  if v_currency is null or upper(coalesce(v_order.currency,'')) <> v_currency then return 'PAYMENT_CURRENCY_MISMATCH'; end if;
  if v_order.payment_provider is not null and lower(v_order.payment_provider) <> p_provider then return 'PAYMENT_PROVIDER_MISMATCH'; end if;
  if v_order.provider_payment_id is not null and v_order.provider_payment_id <> p_provider_payment_id then return 'PAYMENT_INTENT_MISMATCH'; end if;

  select * into v_existing from public.payments
   where payment_provider = p_provider and provider_payment_id = p_provider_payment_id
   limit 1 for update;
  if found and (v_existing.order_id <> p_order_id or v_existing.user_id <> p_user_id) then return 'PAYMENT_BINDING_MISMATCH'; end if;

  if found then
    update public.payments set status='succeeded', amount=p_amount,
      amount_paise=round(p_amount*100)::bigint, currency=v_currency,
      payment_method=coalesce(p_payment_method,payment_method), updated_at=now()
      where id=v_existing.id;
    v_payment_id := v_existing.id;
  else
    insert into public.payments(
      order_id,user_id,stripe_payment_intent_id,payment_provider,provider_payment_id,
      amount,amount_paise,currency,status,payment_method,updated_at
    ) values(
      p_order_id,p_user_id,case when p_provider='stripe' then p_provider_payment_id end,
      p_provider,p_provider_payment_id,p_amount,round(p_amount*100)::bigint,
      v_currency,'succeeded',p_payment_method,now()
    ) returning id into v_payment_id;
  end if;

  select max(a.attempt_number) into v_attempt
    from public.payment_attempts a
   where a.payment_id=v_payment_id and a.provider_payment_id=p_provider_payment_id;

  update public.payment_attempts
     set status='succeeded',
         payment_method=coalesce(p_payment_method,payment_method),
         error_code=null,error_message=null,updated_at=now()
   where payment_id=v_payment_id
     and provider_payment_id=p_provider_payment_id
     and attempt_number=coalesce(v_attempt,attempt_number);

  insert into public.payment_ledger(
    order_id,payment_id,provider,provider_payment_id,entry_type,direction,
    amount,amount_paise,currency,attempt_number,reference,metadata
  ) values(
    p_order_id,v_payment_id,p_provider,p_provider_payment_id,'payment_received',
    'credit',p_amount,round(p_amount*100)::bigint,v_currency,v_attempt,
    p_order_id::text,jsonb_build_object('source','payment_settlement','payment_method',p_payment_method)
  )
  on conflict (provider,provider_payment_id,entry_type)
    where entry_type <> 'payment_refunded'
  do nothing;

  update public.orders set status='paid',payment_provider=p_provider,
    provider_payment_id=p_provider_payment_id,
    stripe_payment_intent=case when p_provider='stripe' then p_provider_payment_id else stripe_payment_intent end,
    paid_at=coalesce(paid_at,now())
   where id=p_order_id;
  return 'SETTLED';
end;
$function$;

revoke execute on function public.settle_payment_transaction(uuid,text,text,numeric,uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.settle_payment_transaction(uuid,text,text,numeric,uuid,text,text)
  to service_role;
