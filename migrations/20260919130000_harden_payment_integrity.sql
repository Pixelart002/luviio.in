-- Payment integrity hardening: reserve replacement retries before creating a new
-- provider PaymentIntent, then bind the reservation to the created intent.

CREATE OR REPLACE FUNCTION public.reserve_payment_retry_replacement(
  p_order_id uuid,
  p_user_id uuid,
  p_window_seconds integer DEFAULT 60,
  p_max_attempts integer DEFAULT 5
)
RETURNS TABLE(reservation_id uuid, attempt_number integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE
  v_made integer;
  v_issued integer;
  v_next integer;
  v_id uuid;
  v_payment_status text;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));

  SELECT status INTO v_payment_status
  FROM public.payments
  WHERE order_id=p_order_id
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_payment_status = 'succeeded' THEN
    RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING ERRCODE='P0001';
  END IF;

  UPDATE public.payment_retry_reservations
     SET status='expired', released_at=COALESCE(released_at,now())
   WHERE order_id=p_order_id AND status='reserved' AND expires_at<=now();

  SELECT count(*)::integer INTO v_made
    FROM public.payment_attempts
   WHERE order_id=p_order_id
     AND created_at>=now()-make_interval(secs=>p_window_seconds);

  SELECT count(*)::integer INTO v_issued
    FROM public.payment_retry_reservations
   WHERE order_id=p_order_id
     AND created_at>=now()-make_interval(secs=>p_window_seconds)
     AND status IN ('reserved','released','expired');

  IF v_made+v_issued>=p_max_attempts THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',p_max_attempts USING ERRCODE='P0001';
  END IF;

  UPDATE public.payment_retry_reservations
     SET status='released', released_at=COALESCE(released_at,now())
   WHERE order_id=p_order_id AND status='reserved' AND expires_at>now();

  v_next:=v_made+v_issued+1;

  INSERT INTO public.payment_retry_reservations(
    order_id,user_id,stripe_payment_intent_id,attempt_number,status,created_at,expires_at,
    payment_provider,provider_payment_id
  ) VALUES (
    p_order_id,p_user_id,'pending-replacement:'||gen_random_uuid(),v_next,'reserved',now(),
    now()+make_interval(secs=>GREATEST(120,p_window_seconds*2)),
    'stripe',NULL
  ) RETURNING id INTO v_id;

  RETURN QUERY SELECT v_id,v_next;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.reserve_payment_retry_replacement(uuid,uuid,integer,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry_replacement(uuid,uuid,integer,integer)
  TO service_role;

CREATE OR REPLACE FUNCTION public.bind_payment_retry_reservation(
  p_reservation_id uuid,
  p_provider text,
  p_provider_payment_id text
)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_updated integer;
BEGIN
  IF p_reservation_id IS NULL OR nullif(trim(p_provider), '') IS NULL
     OR nullif(trim(p_provider_payment_id), '') IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_BINDING_INVALID';
  END IF;

  UPDATE public.payment_retry_reservations
     SET stripe_payment_intent_id=CASE WHEN lower(trim(p_provider))='stripe' THEN trim(p_provider_payment_id) ELSE stripe_payment_intent_id END,
         payment_provider=lower(trim(p_provider)),
         provider_payment_id=trim(p_provider_payment_id)
   WHERE id=p_reservation_id AND status='reserved' AND expires_at>now();

  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated=1;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.bind_payment_retry_reservation(uuid,text,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.bind_payment_retry_reservation(uuid,text,text)
  TO service_role;

CREATE OR REPLACE FUNCTION public.release_payment_retry_reservation(p_reservation_id uuid)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_updated integer;
BEGIN
  UPDATE public.payment_retry_reservations
     SET status='released', released_at=COALESCE(released_at,now())
   WHERE id=p_reservation_id AND status='reserved';
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated=1;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.release_payment_retry_reservation(uuid)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.release_payment_retry_reservation(uuid)
  TO service_role;

-- Return cumulative refund state so application code can distinguish a partial
-- refund from a fully refunded payment/order.
CREATE OR REPLACE FUNCTION public.record_provider_refund_event(
    p_order_id uuid,
    p_provider text,
    p_provider_payment_id text,
    p_provider_refund_id text,
    p_amount numeric,
    p_currency text default 'INR',
    p_status text default 'succeeded',
    p_reason text default null,
    p_metadata jsonb default '{}'::jsonb
)
RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path to 'pg_catalog', 'public'
AS $function$
DECLARE
    v_provider text := lower(nullif(trim(p_provider), ''));
    v_provider_payment_id text := nullif(trim(p_provider_payment_id), '');
    v_provider_refund_id text := nullif(trim(p_provider_refund_id), '');
    v_status text := lower(nullif(trim(p_status), ''));
    v_currency text := upper(coalesce(nullif(trim(p_currency), ''), 'INR'));
    v_payment public.payments%rowtype;
    v_refund public.payment_refunds%rowtype;
    v_attempt integer;
    v_total_refunded numeric;
    v_fully_refunded boolean := false;
BEGIN
    IF p_order_id is null or v_provider is null or v_provider_payment_id is null
       or v_provider_refund_id is null or p_amount is null or p_amount <= 0 THEN
        raise exception 'PROVIDER_REFUND_EVENT_DATA_INVALID';
    END IF;
    IF v_status not in ('pending','succeeded','failed','canceled') THEN
        raise exception 'INVALID_PROVIDER_REFUND_STATUS';
    END IF;

    select * into v_payment
      from public.payments
     where order_id=p_order_id
       and payment_provider=v_provider
       and provider_payment_id=v_provider_payment_id
     order by updated_at desc nulls last, created_at desc nulls last
     limit 1 for update;
    if not found then raise exception 'PAYMENT_NOT_FOUND'; end if;

    select * into v_refund
      from public.payment_refunds
     where payment_provider=v_provider and provider_refund_id=v_provider_refund_id
     for update;

    if found then
        return public.complete_payment_refund_attempt(
            v_refund.id,v_status,v_provider_refund_id,null,null,
            coalesce(p_metadata,'{}'::jsonb) || jsonb_build_object('source','provider_webhook')
        ) || jsonb_build_object('total_refunded',(
            select coalesce(sum(amount),0) from public.payment_refunds
             where payment_id=v_payment.id and status='succeeded'
        ),'fully_refunded',(
            round((select coalesce(sum(amount),0) from public.payment_refunds
             where payment_id=v_payment.id and status='succeeded'),2) >= round(v_payment.amount,2)
        ));
    end if;

    select coalesce(max(refund_attempt_number),0)+1 into v_attempt
      from public.payment_refunds where payment_id=v_payment.id;

    insert into public.payment_refunds(
        payment_id,order_id,refund_attempt_number,payment_provider,provider_payment_id,
        provider_refund_id,idempotency_key,amount,amount_paise,currency,status,reason,
        reference,gateway_metadata
    ) values (
        v_payment.id,p_order_id,v_attempt,v_provider,v_provider_payment_id,
        v_provider_refund_id,'provider-webhook:'||v_provider||':'||v_provider_refund_id,
        round(p_amount,2),round(p_amount*100)::bigint,v_currency,v_status,
        nullif(trim(p_reason),''),v_provider_refund_id,
        coalesce(p_metadata,'{}'::jsonb) || jsonb_build_object('source','provider_webhook')
    ) returning * into v_refund;

    select coalesce(sum(amount),0) into v_total_refunded
      from public.payment_refunds
     where payment_id=v_payment.id and status='succeeded';
    v_fully_refunded := round(v_total_refunded,2) >= round(v_payment.amount,2);

    if v_status='succeeded' and v_fully_refunded then
        update public.payments set status='refunded',updated_at=now() where id=v_payment.id;
    end if;

    if v_status='succeeded' then
        insert into public.payment_ledger(
            order_id,payment_id,provider,provider_payment_id,entry_type,direction,
            amount,amount_paise,currency,attempt_number,reference,metadata
        ) values (
            v_refund.order_id,v_refund.payment_id,v_refund.payment_provider,
            v_refund.provider_payment_id,'payment_refunded','debit',
            v_refund.amount,v_refund.amount_paise,v_refund.currency,
            v_refund.refund_attempt_number,v_refund.provider_refund_id,
            coalesce(v_refund.gateway_metadata,'{}'::jsonb)
              || jsonb_build_object('source','provider_webhook','refund_attempt_id',v_refund.id)
        ) on conflict do nothing;
    end if;

    return jsonb_build_object(
        'id',v_refund.id,'payment_id',v_refund.payment_id,'order_id',v_refund.order_id,
        'refund_attempt_number',v_refund.refund_attempt_number,
        'provider_refund_id',v_refund.provider_refund_id,'status',v_refund.status,
        'amount',v_refund.amount,'amount_paise',v_refund.amount_paise,'currency',v_refund.currency,
        'total_refunded',v_total_refunded,'fully_refunded',v_fully_refunded
    );
end;
$function$;

REVOKE EXECUTE ON FUNCTION public.record_provider_refund_event(uuid,text,text,text,numeric,text,text,text,jsonb)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_provider_refund_event(uuid,text,text,text,numeric,text,text,text,jsonb)
  TO service_role;
