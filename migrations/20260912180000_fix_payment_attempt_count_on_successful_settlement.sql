-- Keep payment attempt accounting authoritative when a reused PaymentIntent succeeds.
-- The retry slot selects the attempt number; settlement persists that attempt as succeeded.

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
  p_order_id uuid,
  p_pi_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL::text,
  p_stripe_currency text DEFAULT NULL::text
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
  v_currency text;
BEGIN
  SELECT * INTO v_order
  FROM public.orders
  WHERE id=p_order_id AND customer_id=p_user_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'PAYMENT_ORDER_NOT_FOUND';
  END IF;

  IF v_order.status='paid' THEN
    RETURN 'ALREADY_PAID';
  END IF;

  IF v_order.status='cancelled' THEN
    RETURN 'ORDER_ALREADY_CANCELLED';
  END IF;

  IF p_amount IS NULL OR p_amount<=0
     OR v_order.total_amount IS NULL
     OR ROUND(p_amount,2)<>ROUND(v_order.total_amount,2) THEN
    RAISE EXCEPTION 'PAYMENT_AMOUNT_MISMATCH';
  END IF;

  v_currency:=UPPER(TRIM(COALESCE(v_order.currency,'')));
  IF v_currency<>'INR' THEN
    RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
  END IF;

  IF p_stripe_currency IS NULL
     OR UPPER(TRIM(p_stripe_currency))<>v_currency THEN
    RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
  END IF;

  IF v_order.stripe_payment_intent IS NOT NULL
     AND v_order.stripe_payment_intent<>p_pi_id THEN
    RAISE EXCEPTION 'PAYMENT_INTENT_MISMATCH';
  END IF;

  SELECT order_id,user_id
  INTO v_payment_order_id,v_payment_user_id
  FROM public.payments
  WHERE stripe_payment_intent_id=p_pi_id
  LIMIT 1;

  IF FOUND AND (v_payment_order_id<>p_order_id OR v_payment_user_id<>p_user_id) THEN
    RAISE EXCEPTION 'PAYMENT_BINDING_MISMATCH';
  END IF;

  -- The active retry reservation owns the next attempt number. If there is
  -- no retry reservation, settlement belongs to the current attempt (#1 for
  -- the initial checkout, or the already-recorded retry attempt).
  SELECT id,attempt_number
  INTO v_reservation_id,v_reserved_attempt
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id
    AND stripe_payment_intent_id=p_pi_id
    AND status='reserved'
    AND expires_at>now()
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  SELECT id,COALESCE(attempt_number,1)
  INTO v_payment_id,v_attempt
  FROM public.payments
  WHERE order_id=p_order_id
  LIMIT 1
  FOR UPDATE;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;
  ELSE
    v_attempt:=GREATEST(COALESCE(v_attempt,1),1);
  END IF;

  INSERT INTO public.payments(
    order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
    payment_method,attempt_number,total_attempts,latest_attempt_number,
    successful_attempt_number,latest_payment_intent_id,last_attempt_at,updated_at
  )
  VALUES(
    p_order_id,p_user_id,p_pi_id,p_amount,ROUND(p_amount*100)::bigint,v_currency,'succeeded',
    p_payment_method,v_attempt,v_attempt,v_attempt,v_attempt,p_pi_id,NOW(),NOW()
  )
  ON CONFLICT (order_id) DO UPDATE SET
    stripe_payment_intent_id=EXCLUDED.stripe_payment_intent_id,
    user_id=EXCLUDED.user_id,
    amount=EXCLUDED.amount,
    amount_paise=EXCLUDED.amount_paise,
    currency=EXCLUDED.currency,
    status='succeeded',
    payment_method=COALESCE(EXCLUDED.payment_method,public.payments.payment_method),
    error_code=NULL,
    error_message=NULL,
    attempt_number=GREATEST(COALESCE(public.payments.attempt_number,1),EXCLUDED.attempt_number),
    total_attempts=GREATEST(COALESCE(public.payments.total_attempts,1),EXCLUDED.attempt_number),
    latest_attempt_number=EXCLUDED.attempt_number,
    successful_attempt_number=EXCLUDED.attempt_number,
    latest_payment_intent_id=EXCLUDED.latest_payment_intent_id,
    last_attempt_at=NOW(),
    updated_at=NOW()
  RETURNING id INTO v_payment_id;

  -- Persist exactly one durable history row for the successful attempt.
  SELECT id INTO v_attempt_id
  FROM public.payment_attempts
  WHERE order_id=p_order_id
    AND stripe_payment_intent_id=p_pi_id
    AND attempt_number=v_attempt
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_attempt_id IS NULL THEN
    INSERT INTO public.payment_attempts(
      payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,
      status,amount,amount_paise,currency,error_message,created_at
    )
    VALUES(
      v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,'succeeded',
      p_amount,ROUND(p_amount*100)::bigint,v_currency,NULL,NOW()
    );
  ELSE
    UPDATE public.payment_attempts
    SET payment_id=v_payment_id,
        user_id=p_user_id,
        status='succeeded',
        amount=p_amount,
        amount_paise=ROUND(p_amount*100)::bigint,
        currency=v_currency,
        error_message=NULL
    WHERE id=v_attempt_id;
  END IF;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations
    SET status='consumed',consumed_at=NOW()
    WHERE id=v_reservation_id AND status='reserved';
  END IF;

  UPDATE public.orders
  SET status='paid',
      stripe_payment_intent=p_pi_id,
      paid_at=COALESCE(paid_at,NOW()),
      payment_method=COALESCE(p_payment_method,'card')
  WHERE id=p_order_id;

  IF v_order.coupon_id IS NOT NULL THEN
    IF NOT public.record_coupon_redemption(
      v_order.coupon_id,p_user_id,p_order_id,COALESCE(v_order.discount_amount,0)
    ) THEN
      RAISE EXCEPTION 'COUPON_REDEMPTION_FAILED';
    END IF;
  END IF;

  RETURN 'SETTLED';
END;
$function$;

-- Repair only deterministic aggregate metadata: a succeeded payment has a
-- successful attempt equal to its current canonical attempt number.
UPDATE public.payments
SET successful_attempt_number=GREATEST(COALESCE(attempt_number,1),1),
    latest_attempt_number=GREATEST(COALESCE(attempt_number,1),1),
    latest_payment_intent_id=COALESCE(latest_payment_intent_id,stripe_payment_intent_id),
    updated_at=NOW()
WHERE status='succeeded'
  AND successful_attempt_number IS NULL;

-- Ensure succeeded payments have at least one durable success record when the
-- canonical aggregate already proves that an attempt occurred. This does not
-- invent intermediate failed attempts.
INSERT INTO public.payment_attempts(
  payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,
  status,amount,amount_paise,currency,error_message,created_at
)
SELECT
  p.id,p.order_id,p.user_id,p.stripe_payment_intent_id,
  GREATEST(COALESCE(p.attempt_number,1),1),
  'succeeded',p.amount,p.amount_paise,p.currency,NULL,COALESCE(p.last_attempt_at,p.updated_at,NOW())
FROM public.payments p
WHERE p.status='succeeded'
  AND p.stripe_payment_intent_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM public.payment_attempts a
    WHERE a.order_id=p.order_id
      AND a.stripe_payment_intent_id=p.stripe_payment_intent_id
      AND a.attempt_number=GREATEST(COALESCE(p.attempt_number,1),1)
  );