-- Separate retry-security reservations from durable payment-attempt accounting.
-- Reservations consume retry capacity, but they are not payment attempts.

CREATE OR REPLACE FUNCTION public.reserve_payment_retry(
  p_order_id uuid,
  p_user_id uuid,
  p_pi_id text,
  p_window_seconds integer DEFAULT NULL,
  p_max_attempts integer DEFAULT NULL
)
RETURNS TABLE(reservation_id uuid, attempt_number integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
declare
  v_policy_max integer;
  v_policy_window integer;
  v_payment_id uuid;
  v_payment_status text;
  v_payment_max integer;
  v_existing uuid;
  v_existing_attempt integer;
  v_next integer;
  v_id uuid;
begin
  if p_order_id is null or p_user_id is null or nullif(trim(p_pi_id),'') is null then
    raise exception 'INVALID_RETRY_ARGUMENTS' using errcode='P0001';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));

  select max_attempts,window_seconds into v_policy_max,v_policy_window
  from public.payment_retry_policy where id=true;
  v_policy_max:=greatest(1,coalesce(v_policy_max,5));
  v_policy_window:=greatest(1,coalesce(v_policy_window,180));

  select p.id,p.status,p.max_attempts into v_payment_id,v_payment_status,v_payment_max
  from public.payments p
  join public.orders o on o.id=p.order_id
  where p.order_id=p_order_id and o.customer_id=p_user_id
    and (p.stripe_payment_intent_id=p_pi_id or p.latest_payment_intent_id=p_pi_id)
  order by p.created_at desc limit 1 for update;

  if v_payment_id is null then
    select p.id,p.status,p.max_attempts into v_payment_id,v_payment_status,v_payment_max
    from public.payments p
    join public.orders o on o.id=p.order_id
    where p.order_id=p_order_id and o.customer_id=p_user_id
    order by p.created_at desc limit 1 for update;
  end if;

  if v_payment_id is null then raise exception 'PAYMENT_NOT_FOUND' using errcode='P0001'; end if;
  if v_payment_status='succeeded' then raise exception 'PAYMENT_ALREADY_SUCCEEDED' using errcode='P0001'; end if;

  v_policy_max:=greatest(1,coalesce(v_payment_max,v_policy_max));

  -- A reservation is retry-security state, not durable payment accounting.
  -- Expired reservations consume retry capacity but never create fake
  -- payment_attempts rows and never increment payments.total_attempts.
  update public.payment_retry_reservations
     set status='expired',released_at=coalesce(released_at,now())
   where order_id=p_order_id and user_id=p_user_id
     and status='reserved' and expires_at<=now();

  select r.id,r.attempt_number into v_existing,v_existing_attempt
  from public.payment_retry_reservations r
  where r.order_id=p_order_id and r.user_id=p_user_id
    and r.stripe_payment_intent_id=p_pi_id and r.status='reserved' and r.expires_at>now()
  order by r.created_at desc limit 1 for update;

  if v_existing is not null then
    return query select v_existing,v_existing_attempt;
    return;
  end if;

  select greatest(
    coalesce((select max(a.attempt_number) from public.payment_attempts a where a.order_id=p_order_id),0),
    coalesce((select max(r.attempt_number) from public.payment_retry_reservations r where r.order_id=p_order_id),0)
  )+1 into v_next;

  if v_next>v_policy_max then
    raise exception 'PAYMENT_RETRY_LIMIT:%',v_policy_max using errcode='P0001';
  end if;

  insert into public.payment_retry_reservations(
    order_id,user_id,stripe_payment_intent_id,attempt_number,status,created_at,expires_at
  ) values(
    p_order_id,p_user_id,p_pi_id,v_next,'reserved',now(),now()+make_interval(secs=>v_policy_window)
  ) returning id into v_id;

  return query select v_id,v_next;
end;
$function$;

REVOKE ALL ON FUNCTION public.reserve_payment_retry(uuid,uuid,text,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry(uuid,uuid,text,integer,integer) TO service_role;

-- Reconcile legacy counter drift. payments.*_attempt fields represent durable
-- payment_attempts history; retry reservations remain separate security state.
UPDATE public.payments p
SET attempt_number=x.max_attempt,
    total_attempts=x.max_attempt,
    latest_attempt_number=x.max_attempt,
    updated_at=now()
FROM (
  SELECT p2.id,COALESCE(MAX(a.attempt_number),0) AS max_attempt
  FROM public.payments p2
  LEFT JOIN public.payment_attempts a ON a.payment_id=p2.id
  GROUP BY p2.id
) x
WHERE p.id=x.id
  AND (p.attempt_number<>x.max_attempt
    OR p.total_attempts<>x.max_attempt
    OR p.latest_attempt_number<>x.max_attempt);
