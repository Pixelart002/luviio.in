-- Same-PI retry accounting: only a reserved retry slot may advance the attempt number.
-- Duplicate client/webhook notifications update the current attempt instead of
-- manufacturing additional attempts.

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
  v_attempt_id uuid;
  v_attempt integer;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_existing_status text;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));

  SELECT p.id INTO v_payment_id
  FROM public.payments AS p
  WHERE p.order_id=p_order_id
  ORDER BY p.created_at
  LIMIT 1;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  -- A retry must have a reservation. Its attempt number is the only authority
  -- allowed to advance the same-PI attempt sequence.
  SELECT r.id,r.attempt_number
    INTO v_reservation_id,v_reserved_attempt
  FROM public.payment_retry_reservations AS r
  WHERE r.order_id=p_order_id
    AND r.user_id=p_user_id
    AND r.stripe_payment_intent_id=p_pi_id
    AND r.status='reserved'
    AND (r.expires_at IS NULL OR r.expires_at>now())
  ORDER BY r.created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;
  ELSE
    -- Initial checkout only: create attempt #1. Once an attempt already exists,
    -- repeated client/webhook notifications update that same attempt.
    SELECT pa.id,pa.attempt_number,pa.status
      INTO v_attempt_id,v_attempt,v_existing_status
    FROM public.payment_attempts AS pa
    WHERE pa.order_id=p_order_id
      AND pa.stripe_payment_intent_id=p_pi_id
    ORDER BY pa.attempt_number DESC,pa.created_at DESC
    LIMIT 1
    FOR UPDATE;

    IF v_attempt_id IS NOT NULL THEN
      UPDATE public.payment_attempts AS pa
      SET status=p_status,
          payment_method=COALESCE(p_payment_method,pa.payment_method),
          error_code=p_error_code,
          error_message=p_error_message,
          ip_address=COALESCE(p_ip_address,pa.ip_address),
          user_agent=COALESCE(p_user_agent,pa.user_agent),
          amount=p_amount,
          amount_paise=ROUND(p_amount*100)::bigint,
          updated_at=now()
      WHERE pa.id=v_attempt_id;
    ELSE
      v_attempt:=1;
    END IF;
  END IF;

  IF v_attempt_id IS NULL THEN
    INSERT INTO public.payment_attempts(
      payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,
      status,amount,amount_paise,currency,payment_method,error_code,error_message,
      ip_address,user_agent,created_at
    ) VALUES (
      v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
      p_amount,ROUND(p_amount*100)::bigint,'INR',p_payment_method,p_error_code,
      p_error_message,p_ip_address,p_user_agent,now()
    ) RETURNING id INTO v_attempt_id;
  END IF;

  UPDATE public.payments AS p SET
    status=p_status,
    payment_method=COALESCE(p_payment_method,p.payment_method),
    error_code=p_error_code,
    error_message=p_error_message,
    attempt_number=GREATEST(COALESCE(p.attempt_number,0),v_attempt),
    total_attempts=GREATEST(COALESCE(p.total_attempts,0),v_attempt),
    latest_attempt_number=GREATEST(COALESCE(p.latest_attempt_number,0),v_attempt),
    latest_payment_intent_id=p_pi_id,
    successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE p.successful_attempt_number END,
    last_attempt_at=now(),
    updated_at=now()
  WHERE p.id=v_payment_id;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations AS r
    SET status='consumed',consumed_at=COALESCE(r.consumed_at,now())
    WHERE r.id=v_reservation_id;
  END IF;
END;
$function$;

GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text) TO service_role;
