-- Make retry-slot allocation idempotent for duplicate/concurrent calls.
-- PaymentPolicy and PaymentService may both request the same retry slot; the
-- second call must reuse the live reservation instead of consuming another slot.

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
  v_existing uuid;
  v_existing_attempt integer;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));

  SELECT status INTO v_payment_status
  FROM public.payments
  WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id
  LIMIT 1;

  IF v_payment_status='succeeded' THEN
    RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING ERRCODE='P0001';
  END IF;

  UPDATE public.payment_retry_reservations
  SET status='expired',released_at=COALESCE(released_at,now())
  WHERE order_id=p_order_id
    AND status='reserved'
    AND expires_at<=now();

  -- A live reservation is already the slot for this retry session.
  -- Reuse it so duplicate policy/service calls cannot increment the limit.
  SELECT id,attempt_number
  INTO v_existing,v_existing_attempt
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id
    AND user_id=p_user_id
    AND status='reserved'
    AND expires_at>now()
  ORDER BY created_at DESC
  LIMIT 1
  FOR UPDATE;

  IF v_existing IS NOT NULL THEN
    RETURN QUERY SELECT v_existing,v_existing_attempt;
    RETURN;
  END IF;

  SELECT count(*)::integer INTO v_made
  FROM public.payment_attempts
  WHERE order_id=p_order_id
    AND created_at>=now()-make_interval(secs=>p_window_seconds)
    AND status<>'reserved';

  SELECT count(*)::integer INTO v_issued
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id
    AND created_at>=now()-make_interval(secs=>p_window_seconds)
    AND status IN ('reserved','released','expired');

  IF v_made+v_issued>=p_max_attempts THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',p_max_attempts USING ERRCODE='P0001';
  END IF;

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
    p_order_id,p_user_id,p_pi_id,v_next,'reserved',now(),
    now()+make_interval(secs=>p_window_seconds)
  )
  RETURNING id INTO v_id;

  RETURN QUERY SELECT v_id,v_next;
END;
$function$;

-- Any retry reservation attached to an already successful payment is no
-- longer usable and must not remain active.
UPDATE public.payment_retry_reservations r
SET status='released',released_at=COALESCE(released_at,NOW())
FROM public.payments p
WHERE r.order_id=p.order_id
  AND r.stripe_payment_intent_id=p.stripe_payment_intent_id
  AND r.status='reserved'
  AND p.status='succeeded';
