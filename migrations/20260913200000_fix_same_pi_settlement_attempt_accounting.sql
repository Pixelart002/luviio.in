-- A PaymentIntent is one durable payment-attempt ledger entry.
-- If the same PI moves from requires_payment_method to succeeded, update
-- that attempt instead of creating Attempt #2. Preserve client metadata and
-- enrich gateway metadata at settlement time.

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
  p_order_id uuid,
  p_pi_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL,
  p_stripe_currency text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_payment_order_id uuid;
  v_payment_user_id uuid;
  v_payment_id uuid;
  v_attempt integer;
  v_attempt_id uuid;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_latest_attempt integer;
  v_latest_status text;
  v_currency text;
  v_gateway jsonb;
BEGIN
  SELECT * INTO v_order
  FROM public.orders
  WHERE id=p_order_id AND customer_id=p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'PAYMENT_ORDER_NOT_FOUND'; END IF;
  IF v_order.status='paid' THEN RETURN 'ALREADY_PAID'; END IF;
  IF v_order.status='cancelled' THEN RETURN 'ORDER_ALREADY_CANCELLED'; END IF;
  IF p_amount IS NULL OR p_amount<=0 OR v_order.total_amount IS NULL OR ROUND(p_amount,2)<>ROUND(v_order.total_amount,2) THEN
    RAISE EXCEPTION 'PAYMENT_AMOUNT_MISMATCH';
  END IF;

  v_currency:=UPPER(TRIM(COALESCE(v_order.currency,'')));
  IF v_currency<>'INR' THEN RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF p_stripe_currency IS NULL OR UPPER(TRIM(p_stripe_currency))<>v_currency THEN RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF v_order.stripe_payment_intent IS NOT NULL AND v_order.stripe_payment_intent<>p_pi_id THEN RAISE EXCEPTION 'PAYMENT_INTENT_MISMATCH'; END IF;

  SELECT order_id,user_id INTO v_payment_order_id,v_payment_user_id
  FROM public.payments WHERE stripe_payment_intent_id=p_pi_id LIMIT 1;
  IF FOUND AND (v_payment_order_id<>p_order_id OR v_payment_user_id<>p_user_id) THEN RAISE EXCEPTION 'PAYMENT_BINDING_MISMATCH'; END IF;

  SELECT id,attempt_number INTO v_reservation_id,v_reserved_attempt
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id AND status='reserved' AND expires_at>now()
  ORDER BY created_at DESC LIMIT 1 FOR UPDATE;

  SELECT id,COALESCE(attempt_number,1) INTO v_payment_id,v_attempt
  FROM public.payments WHERE order_id=p_order_id LIMIT 1 FOR UPDATE;

  -- Same PI = same attempt. Never manufacture a second attempt on settlement.
  SELECT pa.id,pa.attempt_number,pa.status
    INTO v_attempt_id,v_latest_attempt,v_latest_status
  FROM public.payment_attempts pa
  WHERE pa.order_id=p_order_id AND pa.stripe_payment_intent_id=p_pi_id
  ORDER BY pa.attempt_number DESC,pa.created_at DESC
  LIMIT 1 FOR UPDATE;

  IF v_attempt_id IS NOT NULL THEN
    v_attempt:=v_latest_attempt;
  ELSIF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;
  ELSE
    v_attempt:=GREATEST(COALESCE(v_attempt,1),1);
  END IF;

  v_gateway := jsonb_build_object(
    'provider','stripe',
    'payment_intent_id',p_pi_id,
    'order_id',p_order_id,
    'user_id',p_user_id,
    'amount',p_amount,
    'amount_paise',ROUND(p_amount*100)::bigint,
    'currency',v_currency,
    'status','succeeded',
    'payment_method',p_payment_method,
    'error_code',NULL,
    'error_message',NULL,
    'settlement','confirmed'
  );

  INSERT INTO public.payments(
    order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
    payment_method,attempt_number,total_attempts,latest_attempt_number,
    successful_attempt_number,latest_payment_intent_id,last_attempt_at,updated_at
  ) VALUES (
    p_order_id,p_user_id,p_pi_id,p_amount,ROUND(p_amount*100)::bigint,v_currency,'succeeded',
    p_payment_method,v_attempt,v_attempt,v_attempt,v_attempt,p_pi_id,NOW(),NOW()
  )
  ON CONFLICT (order_id) DO UPDATE SET
    stripe_payment_intent_id=EXCLUDED.stripe_payment_intent_id,
    user_id=EXCLUDED.user_id, amount=EXCLUDED.amount, amount_paise=EXCLUDED.amount_paise,
    currency=EXCLUDED.currency,status='succeeded',
    payment_method=COALESCE(EXCLUDED.payment_method,public.payments.payment_method),
    error_code=NULL,error_message=NULL,
    attempt_number=GREATEST(COALESCE(public.payments.attempt_number,1),EXCLUDED.attempt_number),
    total_attempts=GREATEST(COALESCE(public.payments.total_attempts,1),EXCLUDED.attempt_number),
    latest_attempt_number=EXCLUDED.attempt_number,successful_attempt_number=EXCLUDED.attempt_number,
    latest_payment_intent_id=EXCLUDED.latest_payment_intent_id,last_attempt_at=NOW(),updated_at=NOW()
  RETURNING id INTO v_payment_id;

  IF v_attempt_id IS NULL THEN
    INSERT INTO public.payment_attempts(
      payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,
      payment_method,error_code,error_message,gateway_metadata,created_at,updated_at
    ) VALUES (
      v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,'succeeded',p_amount,ROUND(p_amount*100)::bigint,v_currency,
      p_payment_method,NULL,NULL,v_gateway,NOW(),NOW()
    );
  ELSE
    UPDATE public.payment_attempts
    SET payment_id=v_payment_id,user_id=p_user_id,status='succeeded',amount=p_amount,
        amount_paise=ROUND(p_amount*100)::bigint,currency=v_currency,
        payment_method=COALESCE(p_payment_method,payment_method),error_code=NULL,error_message=NULL,
        gateway_metadata=COALESCE(gateway_metadata,'{}'::jsonb) || v_gateway,updated_at=NOW()
    WHERE id=v_attempt_id;
  END IF;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations SET status='consumed',consumed_at=NOW()
    WHERE id=v_reservation_id AND status='reserved';
  END IF;

  UPDATE public.orders
  SET status='paid',stripe_payment_intent=p_pi_id,paid_at=COALESCE(paid_at,NOW()),payment_method=COALESCE(p_payment_method,'card')
  WHERE id=p_order_id;

  IF v_order.coupon_id IS NOT NULL THEN
    IF NOT public.record_coupon_redemption(v_order.coupon_id,p_user_id,p_order_id,COALESCE(v_order.discount_amount,0)) THEN
      RAISE EXCEPTION 'COUPON_REDEMPTION_FAILED';
    END IF;
  END IF;
  RETURN 'SETTLED';
END;
$function$;

GRANT EXECUTE ON FUNCTION public.settle_order_transaction(uuid,text,numeric,uuid,text,text) TO service_role;
