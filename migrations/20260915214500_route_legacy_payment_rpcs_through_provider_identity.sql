-- Compatibility bridge for existing application calls.
-- The public function signatures stay unchanged, but provider identity is now
-- resolved from the payment ledger instead of assuming Stripe.

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
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_provider text;
BEGIN
  SELECT coalesce(
      p.payment_provider,
      CASE WHEN p.stripe_payment_intent_id = p_pi_id OR p.latest_payment_intent_id = p_pi_id THEN 'stripe' END,
      'stripe'
    )
    INTO v_provider
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND (
       p.provider_payment_id = p_pi_id
       OR p.stripe_payment_intent_id = p_pi_id
       OR p.latest_payment_intent_id = p_pi_id
     )
   ORDER BY p.created_at DESC
   LIMIT 1;

  IF v_provider IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  PERFORM public.record_payment_attempt_provider(
    p_order_id,
    p_user_id,
    v_provider,
    p_pi_id,
    p_amount,
    p_status,
    p_payment_method,
    p_error_code,
    p_error_message,
    p_ip_address,
    p_user_agent
  );
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text)
  TO service_role;

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
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_provider text;
  v_result record;
BEGIN
  SELECT coalesce(
      p.payment_provider,
      CASE WHEN p.stripe_payment_intent_id = p_pi_id OR p.latest_payment_intent_id = p_pi_id THEN 'stripe' END,
      'stripe'
    )
    INTO v_provider
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND (
       p.provider_payment_id = p_pi_id
       OR p.stripe_payment_intent_id = p_pi_id
       OR p.latest_payment_intent_id = p_pi_id
     )
   ORDER BY p.created_at DESC
   LIMIT 1;

  IF v_provider IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_NOT_FOUND';
  END IF;

  SELECT * INTO v_result
    FROM public.reserve_payment_retry_provider(
      p_order_id,
      p_user_id,
      v_provider,
      p_pi_id,
      p_window_seconds,
      p_max_attempts
    );

  RETURN QUERY SELECT v_result.reservation_id, v_result.attempt_number;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.reserve_payment_retry(uuid, uuid, text, integer, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry(uuid, uuid, text, integer, integer)
  TO service_role;
