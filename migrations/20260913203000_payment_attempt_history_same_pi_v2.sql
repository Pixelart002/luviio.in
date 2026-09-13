-- Payment attempt history v2.
-- One Stripe PaymentIntent may have multiple real payment tries.
-- payment_attempts is a terminal-attempt ledger, not a PaymentIntent lifecycle row.
-- Initial requires_payment_method/requires_confirmation/requires_action states do
-- not consume an attempt. Each actual failed/succeeded try gets a fresh row,
-- even when Stripe reuses the same PaymentIntent.

DROP INDEX IF EXISTS public.uq_payment_attempts_order_pi;

DROP TRIGGER IF EXISTS trg_track_payment_retry ON public.payments;
DROP FUNCTION IF EXISTS public.trg_track_payment_retry();

DROP FUNCTION IF EXISTS public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text);

CREATE OR REPLACE FUNCTION public.record_payment_attempt(
  p_order_id uuid,
  p_user_id uuid,
  p_pi_id text,
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
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE
  v_payment_id uuid;
  v_attempt integer;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_policy_max integer;
  v_gateway jsonb;
  v_ip text;
  v_ua text;
BEGIN
  IF p_status IN ('requires_payment_method','requires_confirmation','requires_action') THEN
    RETURN;
  END IF;

  -- Client-side reports are advisory. Stripe webhook outcomes are authoritative.
  IF p_status='failed' AND p_payment_method IS NULL AND p_error_code IS NULL THEN
    RETURN;
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));

  SELECT p.id, p.ip_address, p.user_agent
    INTO v_payment_id, v_ip, v_ua
  FROM public.payments p
  WHERE p.order_id=p_order_id
  ORDER BY p.created_at
  LIMIT 1
  FOR UPDATE;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  v_ip := COALESCE(p_ip_address, v_ip);
  v_ua := COALESCE(p_user_agent, v_ua);

  SELECT greatest(1, coalesce(prp.max_attempts,5))
    INTO v_policy_max
  FROM public.payment_retry_policy prp
  WHERE prp.id=true;
  v_policy_max := greatest(1, coalesce(v_policy_max,5));

  SELECT r.id, r.attempt_number
    INTO v_reservation_id, v_reserved_attempt
  FROM public.payment_retry_reservations r
  WHERE r.order_id=p_order_id
    AND r.stripe_payment_intent_id=p_pi_id
    AND r.status='reserved'
    AND r.expires_at>now()
  ORDER BY r.created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt := v_reserved_attempt;
  ELSE
    SELECT COALESCE(MAX(a.attempt_number),0)+1
      INTO v_attempt
    FROM public.payment_attempts a
    WHERE a.order_id=p_order_id;
  END IF;

  IF v_attempt > v_policy_max THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING ERRCODE='P0001';
  END IF;

  v_gateway := jsonb_build_object(
    'provider','stripe','payment_intent_id',p_pi_id,'order_id',p_order_id,
    'user_id',p_user_id,'amount',p_amount,'amount_paise',round(p_amount*100)::bigint,
    'currency','INR','status',p_status,'payment_method',p_payment_method,
    'error_code',p_error_code,'error_message',p_error_message,'record_type','payment_attempt'
  );

  INSERT INTO public.payment_attempts(
    payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,
    amount,amount_paise,currency,payment_method,error_code,error_message,
    ip_address,user_agent,gateway_metadata,created_at,updated_at
  ) VALUES(
    v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
    p_amount,round(p_amount*100)::bigint,'INR',p_payment_method,p_error_code,p_error_message,
    v_ip,v_ua,v_gateway,now(),now()
  );

  UPDATE public.payments
  SET status=p_status,
      payment_method=COALESCE(p_payment_method,payment_method),
      error_code=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_code END,
      error_message=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_message END,
      attempt_number=GREATEST(COALESCE(attempt_number,0),v_attempt),
      total_attempts=GREATEST(COALESCE(total_attempts,0),v_attempt),
      latest_attempt_number=v_attempt,
      latest_payment_intent_id=p_pi_id,
      successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,
      ip_address=COALESCE(v_ip,ip_address),user_agent=COALESCE(v_ua,user_agent),
      gateway_metadata=v_gateway,last_attempt_at=now(),updated_at=now()
  WHERE id=v_payment_id;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations
    SET status='consumed',consumed_at=COALESCE(consumed_at,now())
    WHERE id=v_reservation_id AND status='reserved';
  END IF;
END;
$function$;

REVOKE ALL ON FUNCTION public.record_payment_attempt(uuid,uuid,text,numeric,text,text,text,text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid,uuid,text,numeric,text,text,text,text,text,text) TO service_role;

DROP FUNCTION IF EXISTS public.settle_order_transaction(uuid,text,numeric,uuid,text,text);

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
  p_order_id uuid,
  p_pi_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL,
  p_stripe_currency text DEFAULT NULL,
  p_ip_address text DEFAULT NULL,
  p_user_agent text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_currency text;
  v_bound_order uuid;
  v_bound_user uuid;
BEGIN
  SELECT * INTO v_order FROM public.orders WHERE id=p_order_id AND customer_id=p_user_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'PAYMENT_ORDER_NOT_FOUND'; END IF;
  IF v_order.status='paid' THEN RETURN 'ALREADY_PAID'; END IF;
  IF v_order.status='cancelled' THEN RETURN 'ORDER_ALREADY_CANCELLED'; END IF;
  IF p_amount IS NULL OR p_amount<=0 OR v_order.total_amount IS NULL OR round(p_amount,2)<>round(v_order.total_amount,2) THEN RAISE EXCEPTION 'PAYMENT_AMOUNT_MISMATCH'; END IF;

  v_currency:=upper(trim(coalesce(v_order.currency,'')));
  IF v_currency<>'INR' THEN RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF p_stripe_currency IS NOT NULL AND upper(trim(p_stripe_currency))<>v_currency THEN RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF v_order.stripe_payment_intent IS NOT NULL AND v_order.stripe_payment_intent<>p_pi_id THEN RAISE EXCEPTION 'PAYMENT_INTENT_MISMATCH'; END IF;

  SELECT p.order_id,p.user_id INTO v_bound_order,v_bound_user
  FROM public.payments p
  WHERE p.stripe_payment_intent_id=p_pi_id OR (p.order_id=p_order_id AND p.latest_payment_intent_id=p_pi_id)
  ORDER BY p.created_at LIMIT 1;
  IF v_bound_order IS NOT NULL AND (v_bound_order<>p_order_id OR v_bound_user<>p_user_id) THEN RAISE EXCEPTION 'PAYMENT_BINDING_MISMATCH'; END IF;

  -- A successful retry on the same PaymentIntent is a new durable attempt row.
  PERFORM public.record_payment_attempt(
    p_order_id,p_user_id,p_pi_id,p_amount,'succeeded',p_payment_method,NULL,NULL,
    p_ip_address,p_user_agent
  );

  UPDATE public.orders
  SET status='paid',stripe_payment_intent=p_pi_id,paid_at=COALESCE(paid_at,now()),payment_method=COALESCE(p_payment_method,'card')
  WHERE id=p_order_id;

  IF v_order.coupon_id IS NOT NULL THEN
    IF NOT public.record_coupon_redemption(v_order.coupon_id,p_user_id,p_order_id,coalesce(v_order.discount_amount,0)) THEN
      RAISE EXCEPTION 'COUPON_REDEMPTION_FAILED';
    END IF;
  END IF;
  RETURN 'SETTLED';
END;
$function$;

GRANT EXECUTE ON FUNCTION public.settle_order_transaction(uuid,text,numeric,uuid,text,text,text,text) TO service_role;
