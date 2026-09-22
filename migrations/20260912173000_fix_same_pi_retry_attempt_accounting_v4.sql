-- Fix same-PaymentIntent retry accounting.
-- A retry reservation is the authoritative slot; payment_attempts stores its durable outcome.
-- Do not count the same retry twice (reservation + attempt row).

CREATE OR REPLACE FUNCTION public.reserve_payment_retry(
  p_order_id uuid,
  p_user_id uuid,
  p_pi_id text,
  p_window_seconds integer DEFAULT 60,
  p_max_attempts integer DEFAULT 5
)
RETURNS TABLE(reservation_id uuid, attempt_number integer)
LANGUAGE plpgsql
SECURITY DEFINER
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

  -- Never issue a retry slot after the canonical payment has already succeeded.
  SELECT status INTO v_payment_status
  FROM public.payments
  WHERE order_id=p_order_id
    AND stripe_payment_intent_id=p_pi_id
  LIMIT 1;

  IF v_payment_status='succeeded' THEN
    RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING ERRCODE='P0001';
  END IF;

  -- Expire stale reservations first.
  UPDATE public.payment_retry_reservations
  SET status='expired',released_at=COALESCE(released_at,now())
  WHERE order_id=p_order_id
    AND status='reserved'
    AND expires_at<=now();

  -- payment_attempts contains durable outcomes. A still-reserved attempt is
  -- already represented by payment_retry_reservations, so exclude it here.
  SELECT count(*)::integer INTO v_made
  FROM public.payment_attempts
  WHERE order_id=p_order_id
    AND created_at>=now()-make_interval(secs=>p_window_seconds)
    AND status<>'reserved';

  -- Reservations represent retry slots that have been issued but do not yet
  -- have a durable outcome. Released/expired slots still count within the
  -- rolling window so callers cannot bypass the 5-attempt limit by releasing
  -- and immediately reserving again.
  SELECT count(*)::integer INTO v_issued
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id
    AND created_at>=now()-make_interval(secs=>p_window_seconds)
    AND status IN ('reserved','released','expired');

  IF v_made+v_issued>=p_max_attempts THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',p_max_attempts USING ERRCODE='P0001';
  END IF;

  -- Supersede the previous active retry session for this order.
  UPDATE public.payment_retry_reservations
  SET status='released',released_at=now()
  WHERE order_id=p_order_id
    AND status='reserved'
    AND expires_at>now();

  v_next:=v_made+v_issued+1;

  INSERT INTO public.payment_retry_reservations(
    order_id,user_id,stripe_payment_intent_id,attempt_number,status,created_at,expires_at
  )
  VALUES(
    p_order_id,p_user_id,p_pi_id,v_next,'reserved',now(),now()+interval '120 seconds'
  )
  RETURNING id INTO v_id;

  RETURN QUERY SELECT v_id,v_next;
END;
$function$;

CREATE OR REPLACE FUNCTION public.record_payment_attempt(
  p_order_id uuid,
  p_user_id uuid,
  p_pi_id text,
  p_amount numeric,
  p_status text,
  p_payment_method text DEFAULT NULL::text,
  p_error_code text DEFAULT NULL::text,
  p_error_message text DEFAULT NULL::text,
  p_ip_address text DEFAULT NULL::text,
  p_user_agent text DEFAULT NULL::text
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
BEGIN
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

  IF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;

    -- Reuse the attempt row created/owned by the retry slot instead of
    -- creating a second row for the same retry.
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
        v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
        p_amount,ROUND(p_amount*100)::bigint,'INR',p_error_message,now()
      );
    ELSE
      UPDATE public.payment_attempts
      SET status=p_status,
          amount=p_amount,
          amount_paise=ROUND(p_amount*100)::bigint,
          error_message=p_error_message
      WHERE id=v_attempt_id;
    END IF;

    UPDATE public.payment_retry_reservations
    SET status='consumed',consumed_at=now()
    WHERE id=v_reservation_id;
  ELSE
    SELECT id,attempt_number INTO v_attempt_id,v_attempt
    FROM public.payment_attempts
    WHERE order_id=p_order_id
      AND stripe_payment_intent_id=p_pi_id
      AND status IN ('requires_payment_method','requires_confirmation','requires_action','processing','reserved')
    ORDER BY attempt_number DESC,created_at DESC
    LIMIT 1;

    IF v_attempt_id IS NOT NULL THEN
      UPDATE public.payment_attempts
      SET status=p_status,
          error_message=p_error_message,
          amount=p_amount,
          amount_paise=ROUND(p_amount*100)::bigint
      WHERE id=v_attempt_id;
    ELSE
      SELECT COALESCE(MAX(attempt_number),0)+1
      INTO v_attempt
      FROM public.payment_attempts
      WHERE order_id=p_order_id;

      INSERT INTO public.payment_attempts(
        payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,
        status,amount,amount_paise,currency,error_message,created_at
      )
      VALUES(
        v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
        p_amount,ROUND(p_amount*100)::bigint,'INR',p_error_message,now()
      );
    END IF;
  END IF;

  UPDATE public.payments SET
    status=p_status,
    payment_method=COALESCE(p_payment_method,payment_method),
    error_code=COALESCE(p_error_code,error_code),
    error_message=COALESCE(p_error_message,error_message),
    attempt_number=v_attempt,
    total_attempts=GREATEST(COALESCE(total_attempts,0),v_attempt),
    latest_attempt_number=v_attempt,
    latest_payment_intent_id=p_pi_id,
    successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,
    last_attempt_at=now(),
    updated_at=now()
  WHERE id=v_payment_id;
END;
$function$;

-- Remove stale retry sessions that survived after a payment already succeeded.
UPDATE public.payment_retry_reservations rr
SET status='released',released_at=COALESCE(released_at,now())
FROM public.payments p
WHERE p.order_id=rr.order_id
  AND p.stripe_payment_intent_id=rr.stripe_payment_intent_id
  AND p.status='succeeded'
  AND rr.status='reserved';
