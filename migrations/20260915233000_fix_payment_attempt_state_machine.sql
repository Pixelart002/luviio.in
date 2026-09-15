-- Payment attempt lifecycle fix.
-- Initial PaymentIntent state is requires_payment_method.
-- A real Pay/confirmation updates that same attempt to processing/failed/succeeded.
-- A retry reservation is not itself an attempt; it becomes an attempt only when Stripe reports a result.

CREATE OR REPLACE FUNCTION public.record_payment_attempt_provider(
  p_order_id uuid,
  p_user_id uuid,
  p_provider text,
  p_provider_payment_id text,
  p_amount numeric,
  p_status text,
  p_payment_method text DEFAULT NULL,
  p_error_code text DEFAULT NULL,
  p_error_message text DEFAULT NULL,
  p_ip_address text DEFAULT NULL,
  p_user_agent text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_provider text := lower(nullif(trim(p_provider), ''));
  v_payment_id uuid;
  v_existing_attempt_id uuid;
  v_existing_attempt_number integer;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_attempt integer;
  v_policy_max integer;
  v_payment_max integer;
  v_gateway jsonb;
BEGIN
  IF v_provider IS NULL OR nullif(trim(p_provider_payment_id), '') IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_IDENTITY_INVALID';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text || ':' || v_provider || ':' || p_provider_payment_id, 0));

  SELECT p.id, p.max_attempts INTO v_payment_id, v_payment_max
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND p.user_id = p_user_id
     AND (p.payment_provider = v_provider OR p.stripe_payment_intent_id = p_provider_payment_id OR p.provider_payment_id = p_provider_payment_id)
   ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE;

  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND'; END IF;

  SELECT greatest(1, coalesce(v_payment_max, prp.max_attempts, 5)) INTO v_policy_max
    FROM public.payment_retry_policy prp WHERE prp.id = true;
  v_policy_max := greatest(1, coalesce(v_policy_max, 5));

  SELECT r.id, r.attempt_number INTO v_reservation_id, v_reserved_attempt
    FROM public.payment_retry_reservations r
   WHERE r.order_id = p_order_id AND r.user_id = p_user_id
     AND r.payment_provider = v_provider AND r.provider_payment_id = p_provider_payment_id
     AND r.status = 'reserved' AND r.expires_at > now()
   ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;

  SELECT a.id, a.attempt_number INTO v_existing_attempt_id, v_existing_attempt_number
    FROM public.payment_attempts a
   WHERE a.order_id = p_order_id AND a.payment_provider = v_provider
     AND a.provider_payment_id = p_provider_payment_id
   ORDER BY a.attempt_number DESC, a.created_at DESC LIMIT 1 FOR UPDATE;

  -- Without a higher retry reservation this is the same PaymentIntent attempt.
  -- Update it; never create duplicate rows from client + webhook reports.
  IF v_existing_attempt_id IS NOT NULL
     AND (v_reservation_id IS NULL OR v_reserved_attempt <= v_existing_attempt_number) THEN
    UPDATE public.payment_attempts
       SET status = p_status,
           payment_method = coalesce(p_payment_method, payment_method),
           error_code = CASE WHEN p_status IN ('succeeded','processing','requires_payment_method','requires_confirmation','requires_action') THEN NULL ELSE coalesce(p_error_code, error_code) END,
           error_message = CASE WHEN p_status IN ('succeeded','processing','requires_payment_method','requires_confirmation','requires_action') THEN NULL ELSE coalesce(p_error_message, error_message) END,
           amount = p_amount,
           amount_paise = round(p_amount * 100)::bigint,
           ip_address = coalesce(p_ip_address, ip_address),
           user_agent = coalesce(p_user_agent, user_agent),
           gateway_metadata = jsonb_build_object('provider', v_provider, 'provider_payment_id', p_provider_payment_id, 'status', p_status, 'payment_method', p_payment_method, 'error_code', p_error_code, 'error_message', p_error_message),
           updated_at = now()
     WHERE id = v_existing_attempt_id;

    UPDATE public.payments
       SET status = p_status,
           payment_provider = v_provider,
           provider_payment_id = p_provider_payment_id,
           stripe_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE stripe_payment_intent_id END,
           payment_method = coalesce(p_payment_method, payment_method),
           error_code = CASE WHEN p_status = 'succeeded' THEN NULL ELSE p_error_code END,
           error_message = CASE WHEN p_status = 'succeeded' THEN NULL ELSE p_error_message END,
           attempt_number = greatest(coalesce(attempt_number, 0), v_existing_attempt_number),
           total_attempts = greatest(coalesce(total_attempts, 0), v_existing_attempt_number),
           latest_attempt_number = v_existing_attempt_number,
           latest_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE latest_payment_intent_id END,
           successful_attempt_number = CASE WHEN p_status = 'succeeded' THEN v_existing_attempt_number ELSE successful_attempt_number END,
           ip_address = coalesce(p_ip_address, ip_address),
           user_agent = coalesce(p_user_agent, user_agent),
           last_attempt_at = now(), updated_at = now()
     WHERE id = v_payment_id;

    IF v_reservation_id IS NOT NULL THEN
      UPDATE public.payment_retry_reservations SET status='consumed', consumed_at=coalesce(consumed_at,now()) WHERE id=v_reservation_id;
    END IF;
    RETURN;
  END IF;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt := v_reserved_attempt;
  ELSE
    SELECT coalesce(max(a.attempt_number),0)+1 INTO v_attempt FROM public.payment_attempts a WHERE a.order_id=p_order_id;
  END IF;

  IF v_attempt > v_policy_max THEN RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING ERRCODE='P0001'; END IF;

  v_gateway := jsonb_build_object('provider',v_provider,'provider_payment_id',p_provider_payment_id,'order_id',p_order_id,'user_id',p_user_id,'amount',p_amount,'amount_paise',round(p_amount*100)::bigint,'currency','INR','status',p_status,'payment_method',p_payment_method,'error_code',p_error_code,'error_message',p_error_message,'record_type','payment_attempt');

  INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,payment_provider,provider_payment_id,attempt_number,status,amount,amount_paise,currency,payment_method,error_code,error_message,ip_address,user_agent,gateway_metadata,created_at,updated_at)
  VALUES(v_payment_id,p_order_id,p_user_id,CASE WHEN v_provider='stripe' THEN p_provider_payment_id ELSE NULL END,v_provider,p_provider_payment_id,v_attempt,p_status,p_amount,round(p_amount*100)::bigint,'INR',p_payment_method,p_error_code,p_error_message,p_ip_address,p_user_agent,v_gateway,now(),now());

  UPDATE public.payments
     SET status=p_status,payment_provider=v_provider,provider_payment_id=p_provider_payment_id,
         stripe_payment_intent_id=CASE WHEN v_provider='stripe' THEN p_provider_payment_id ELSE stripe_payment_intent_id END,
         payment_method=coalesce(p_payment_method,payment_method),
         error_code=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_code END,
         error_message=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_message END,
         attempt_number=greatest(coalesce(attempt_number,0),v_attempt),
         total_attempts=greatest(coalesce(total_attempts,0),v_attempt),
         latest_attempt_number=v_attempt,
         latest_payment_intent_id=CASE WHEN v_provider='stripe' THEN p_provider_payment_id ELSE latest_payment_intent_id END,
         successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,
         ip_address=coalesce(p_ip_address,ip_address),user_agent=coalesce(p_user_agent,user_agent),
         gateway_metadata=v_gateway,last_attempt_at=now(),updated_at=now()
   WHERE id=v_payment_id;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations SET status='consumed',consumed_at=coalesce(consumed_at,now()) WHERE id=v_reservation_id;
  END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.reserve_payment_retry_provider(
  p_order_id uuid,p_user_id uuid,p_provider text,p_provider_payment_id text,
  p_window_seconds integer DEFAULT NULL,p_max_attempts integer DEFAULT NULL
)
RETURNS TABLE(reservation_id uuid,attempt_number integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_catalog,pg_temp
AS $function$
DECLARE
  v_provider text:=lower(nullif(trim(p_provider),'')); v_payment_id uuid; v_payment_status text;
  v_payment_max integer; v_policy_max integer; v_policy_window integer;
  v_latest_status text; v_latest_attempt integer; v_existing uuid; v_existing_attempt integer;
  v_next integer; v_id uuid;
BEGIN
  IF v_provider IS NULL OR nullif(trim(p_provider_payment_id),'') IS NULL THEN RAISE EXCEPTION 'PAYMENT_IDENTITY_INVALID'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text||':'||v_provider||':'||p_provider_payment_id,0));

  SELECT p.id,p.status,p.max_attempts INTO v_payment_id,v_payment_status,v_payment_max FROM public.payments p
   WHERE p.order_id=p_order_id AND (p.payment_provider=v_provider OR p.provider_payment_id=p_provider_payment_id OR p.stripe_payment_intent_id=p_provider_payment_id)
   ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE;
  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_NOT_FOUND'; END IF;
  IF v_payment_status='succeeded' THEN RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING ERRCODE='P0001'; END IF;

  v_policy_max:=greatest(1,coalesce(p_max_attempts,v_payment_max,(SELECT max_attempts FROM public.payment_retry_policy WHERE id=true),5));
  v_policy_window:=greatest(1,coalesce(p_window_seconds,(SELECT window_seconds FROM public.payment_retry_policy WHERE id=true),180));

  SELECT a.status,a.attempt_number INTO v_latest_status,v_latest_attempt FROM public.payment_attempts a
   WHERE a.order_id=p_order_id AND a.payment_provider=v_provider AND a.provider_payment_id=p_provider_payment_id
   ORDER BY a.attempt_number DESC,a.created_at DESC LIMIT 1;

  -- No payment submission yet: do not reserve or count another attempt.
  IF v_latest_status IN ('requires_payment_method','requires_confirmation','requires_action','processing') THEN
    RETURN QUERY SELECT NULL::uuid,v_latest_attempt; RETURN;
  END IF;

  SELECT r.id,r.attempt_number INTO v_existing,v_existing_attempt FROM public.payment_retry_reservations r
   WHERE r.order_id=p_order_id AND r.user_id=p_user_id AND r.payment_provider=v_provider AND r.provider_payment_id=p_provider_payment_id
     AND r.status='reserved' AND r.expires_at>now()
   ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;
  IF v_existing IS NOT NULL THEN RETURN QUERY SELECT v_existing,v_existing_attempt; RETURN; END IF;

  SELECT greatest(coalesce((SELECT max(a.attempt_number) FROM public.payment_attempts a WHERE a.order_id=p_order_id),0),coalesce((SELECT max(r.attempt_number) FROM public.payment_retry_reservations r WHERE r.order_id=p_order_id),0))+1 INTO v_next;
  IF v_next>v_policy_max THEN RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING ERRCODE='P0001'; END IF;

  INSERT INTO public.payment_retry_reservations(order_id,user_id,stripe_payment_intent_id,payment_provider,provider_payment_id,attempt_number,status,created_at,expires_at)
  VALUES(p_order_id,p_user_id,CASE WHEN v_provider='stripe' THEN p_provider_payment_id ELSE NULL END,v_provider,p_provider_payment_id,v_next,'reserved',now(),now()+make_interval(secs=>v_policy_window))
  RETURNING id INTO v_id;

  UPDATE public.payments SET max_attempts=v_policy_max,provider_payment_id=p_provider_payment_id,payment_provider=v_provider,updated_at=now() WHERE id=v_payment_id;
  RETURN QUERY SELECT v_id,v_next;
END;
$function$;