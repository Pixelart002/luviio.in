-- Count a second real confirmation on the same PaymentIntent as a new attempt
-- when the previous attempt reached a failed payment-method state.
-- Non-failed Stripe lifecycle callbacks remain updates to the existing attempt.

DROP FUNCTION IF EXISTS public.record_payment_attempt(uuid, uuid, uuid, text, text, numeric, integer, text, text);

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
  v_attempt_id uuid;
  v_attempt integer;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_existing_status text;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text, 0));

  SELECT id INTO v_payment_id
  FROM public.payments
  WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id
  LIMIT 1;

  IF v_payment_id IS NULL THEN
    SELECT id INTO v_payment_id
    FROM public.payments
    WHERE order_id=p_order_id
    LIMIT 1;
  END IF;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  SELECT id,attempt_number INTO v_reservation_id,v_reserved_attempt
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id
    AND user_id=p_user_id
    AND stripe_payment_intent_id=p_pi_id
    AND status='reserved'
    AND expires_at>now()
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;
  ELSE
    SELECT id,attempt_number,status
    INTO v_attempt_id,v_attempt,v_existing_status
    FROM public.payment_attempts
    WHERE order_id=p_order_id
      AND stripe_payment_intent_id=p_pi_id
    ORDER BY attempt_number DESC,created_at DESC
    LIMIT 1
    FOR UPDATE;

    IF v_attempt_id IS NOT NULL
       AND v_existing_status NOT IN ('failed','requires_payment_method','canceled','cancelled') THEN
      UPDATE public.payment_attempts
      SET status=p_status,
          error_message=p_error_message,
          amount=p_amount,
          amount_paise=ROUND(p_amount*100)::bigint,
          updated_at=now()
      WHERE id=v_attempt_id;
    ELSE
      v_attempt:=COALESCE(v_attempt,0)+1;
      v_attempt_id:=NULL;
    END IF;
  END IF;

  IF v_attempt_id IS NULL THEN
    INSERT INTO public.payment_attempts(
      payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,
      status,amount,amount_paise,currency,error_message,created_at
    ) VALUES (
      v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
      p_amount,ROUND(p_amount*100)::bigint,'INR',p_error_message,now()
    ) RETURNING id INTO v_attempt_id;
  END IF;

  UPDATE public.payments SET
    status=p_status,
    payment_method=COALESCE(p_payment_method,payment_method),
    error_code=COALESCE(p_error_code,error_code),
    error_message=COALESCE(p_error_message,error_message),
    attempt_number=GREATEST(COALESCE(attempt_number,0),v_attempt),
    total_attempts=GREATEST(COALESCE(total_attempts,0),v_attempt),
    latest_attempt_number=v_attempt,
    latest_payment_intent_id=p_pi_id,
    successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,
    last_attempt_at=now(),
    updated_at=now()
  WHERE id=v_payment_id;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations
    SET status='consumed',consumed_at=COALESCE(consumed_at,now())
    WHERE id=v_reservation_id;
  END IF;
END;
$function$;

GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text) TO service_role;
