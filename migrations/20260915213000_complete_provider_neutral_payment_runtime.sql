-- Complete the provider-neutral runtime contract introduced by
-- 20260915200000_provider_neutral_payment_identity.sql.
-- Legacy Stripe columns/functions remain for historical compatibility.

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
  v_attempt_id uuid;
  v_attempt integer;
  v_reservation_id uuid;
  v_reserved_attempt integer;
  v_payment_status text;
  v_payment_max integer;
  v_policy_max integer;
  v_gateway jsonb;
BEGIN
  IF v_provider IS NULL OR nullif(trim(p_provider_payment_id), '') IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_IDENTITY_INVALID';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text || ':' || v_provider || ':' || p_provider_payment_id, 0));

  SELECT p.id, p.status, p.max_attempts
    INTO v_payment_id, v_payment_status, v_payment_max
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND p.payment_provider = v_provider
     AND p.provider_payment_id = p_provider_payment_id
   ORDER BY p.created_at DESC
   LIMIT 1
   FOR UPDATE;

  IF v_payment_id IS NULL THEN
    SELECT p.id, p.status, p.max_attempts
      INTO v_payment_id, v_payment_status, v_payment_max
      FROM public.payments p
     WHERE p.order_id = p_order_id
     ORDER BY p.created_at DESC
     LIMIT 1
     FOR UPDATE;
  END IF;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  SELECT greatest(1, coalesce(prp.max_attempts, 5))
    INTO v_policy_max
    FROM public.payment_retry_policy prp
   WHERE prp.id = true;
  v_policy_max := greatest(1, coalesce(v_payment_max, v_policy_max, 5));

  v_gateway := jsonb_build_object(
    'provider', v_provider,
    'provider_payment_id', p_provider_payment_id,
    'order_id', p_order_id,
    'user_id', p_user_id,
    'amount', p_amount,
    'amount_paise', round(p_amount * 100)::bigint,
    'currency', 'INR',
    'status', p_status,
    'payment_method', p_payment_method,
    'error_code', p_error_code,
    'error_message', p_error_message
  );

  SELECT r.id, r.attempt_number
    INTO v_reservation_id, v_reserved_attempt
    FROM public.payment_retry_reservations r
   WHERE r.order_id = p_order_id
     AND r.user_id = p_user_id
     AND r.payment_provider = v_provider
     AND r.provider_payment_id = p_provider_payment_id
     AND r.status = 'reserved'
     AND r.expires_at > now()
   ORDER BY r.created_at DESC
   LIMIT 1
   FOR UPDATE;

  IF v_reservation_id IS NOT NULL THEN
    v_attempt := v_reserved_attempt;
  ELSE
    SELECT pa.id, pa.attempt_number
      INTO v_attempt_id, v_attempt
      FROM public.payment_attempts pa
     WHERE pa.order_id = p_order_id
       AND pa.payment_provider = v_provider
       AND pa.provider_payment_id = p_provider_payment_id
     ORDER BY pa.attempt_number DESC, pa.created_at DESC
     LIMIT 1
     FOR UPDATE;

    IF v_attempt_id IS NOT NULL THEN
      UPDATE public.payment_attempts
         SET status = p_status,
             payment_method = coalesce(p_payment_method, payment_method),
             error_code = coalesce(p_error_code, error_code),
             error_message = coalesce(p_error_message, error_message),
             ip_address = coalesce(p_ip_address, ip_address),
             user_agent = coalesce(p_user_agent, user_agent),
             amount = p_amount,
             amount_paise = round(p_amount * 100)::bigint,
             gateway_metadata = v_gateway,
             updated_at = now()
       WHERE id = v_attempt_id;
    ELSE
      SELECT greatest(
        coalesce((SELECT max(a.attempt_number) FROM public.payment_attempts a WHERE a.order_id = p_order_id), 0),
        coalesce((SELECT max(r.attempt_number) FROM public.payment_retry_reservations r WHERE r.order_id = p_order_id), 0)
      ) + 1
        INTO v_attempt;
      IF v_attempt > v_policy_max THEN
        RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%', v_policy_max USING errcode = 'P0001';
      END IF;
    END IF;
  END IF;

  IF v_attempt_id IS NULL THEN
    INSERT INTO public.payment_attempts (
      payment_id, order_id, user_id, stripe_payment_intent_id,
      payment_provider, provider_payment_id,
      attempt_number, status, amount, amount_paise, currency,
      payment_method, error_code, error_message,
      ip_address, user_agent, gateway_metadata, created_at, updated_at
    ) VALUES (
      v_payment_id, p_order_id, p_user_id,
      CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE NULL END,
      v_provider, p_provider_payment_id,
      v_attempt, p_status, p_amount, round(p_amount * 100)::bigint, 'INR',
      p_payment_method, p_error_code, p_error_message,
      p_ip_address, p_user_agent, v_gateway, now(), now()
    )
    RETURNING id INTO v_attempt_id;
  END IF;

  UPDATE public.payments
     SET status = p_status,
         payment_provider = v_provider,
         provider_payment_id = p_provider_payment_id,
         stripe_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE stripe_payment_intent_id END,
         payment_method = coalesce(p_payment_method, payment_method),
         error_code = coalesce(p_error_code, error_code),
         error_message = coalesce(p_error_message, error_message),
         attempt_number = greatest(coalesce(attempt_number, 0), v_attempt),
         total_attempts = greatest(coalesce(total_attempts, 0), v_attempt),
         latest_attempt_number = greatest(coalesce(latest_attempt_number, 0), v_attempt),
         latest_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE latest_payment_intent_id END,
         successful_attempt_number = CASE WHEN p_status = 'succeeded' THEN v_attempt ELSE successful_attempt_number END,
         ip_address = coalesce(p_ip_address, ip_address),
         user_agent = coalesce(p_user_agent, user_agent),
         gateway_metadata = v_gateway,
         last_attempt_at = now(),
         updated_at = now()
   WHERE id = v_payment_id;

  IF v_reservation_id IS NOT NULL THEN
    UPDATE public.payment_retry_reservations
       SET status = 'consumed', consumed_at = coalesce(consumed_at, now())
     WHERE id = v_reservation_id;
  END IF;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.record_payment_attempt_provider(uuid, uuid, text, text, numeric, text, text, text, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_payment_attempt_provider(uuid, uuid, text, text, numeric, text, text, text, text, text, text)
  TO service_role;

CREATE OR REPLACE FUNCTION public.reserve_payment_retry_provider(
  p_order_id uuid,
  p_user_id uuid,
  p_provider text,
  p_provider_payment_id text,
  p_window_seconds integer DEFAULT NULL,
  p_max_attempts integer DEFAULT NULL
)
RETURNS TABLE(reservation_id uuid, attempt_number integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_provider text := lower(nullif(trim(p_provider), ''));
  v_policy_max integer;
  v_policy_window integer;
  v_payment_id uuid;
  v_payment_status text;
  v_payment_max integer;
  v_existing uuid;
  v_existing_attempt integer;
  v_next integer;
  v_id uuid;
  v_expired record;
BEGIN
  IF v_provider IS NULL OR nullif(trim(p_provider_payment_id), '') IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_IDENTITY_INVALID';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text || ':' || v_provider || ':' || p_provider_payment_id, 0));

  SELECT max_attempts, window_seconds
    INTO v_policy_max, v_policy_window
    FROM public.payment_retry_policy
   WHERE id = true;
  v_policy_max := coalesce(p_max_attempts, v_policy_max, 5);
  v_policy_window := coalesce(p_window_seconds, v_policy_window, 180);

  SELECT p.id, p.status, p.max_attempts
    INTO v_payment_id, v_payment_status, v_payment_max
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND p.payment_provider = v_provider
     AND p.provider_payment_id = p_provider_payment_id
   ORDER BY p.created_at DESC
   LIMIT 1
   FOR UPDATE;

  IF v_payment_id IS NULL THEN
    SELECT p.id, p.status, p.max_attempts
      INTO v_payment_id, v_payment_status, v_payment_max
      FROM public.payments p
     WHERE p.order_id = p_order_id
     ORDER BY p.created_at DESC
     LIMIT 1
     FOR UPDATE;
  END IF;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_NOT_FOUND';
  END IF;
  IF v_payment_status = 'succeeded' THEN
    RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING errcode = 'P0001';
  END IF;

  v_policy_max := coalesce(v_payment_max, v_policy_max, 5);

  FOR v_expired IN
    SELECT r.*
      FROM public.payment_retry_reservations r
     WHERE r.order_id = p_order_id
       AND r.status = 'reserved'
       AND r.expires_at <= now()
     ORDER BY r.created_at
     FOR UPDATE
  LOOP
    IF NOT EXISTS (
      SELECT 1 FROM public.payment_attempts a
       WHERE a.order_id = v_expired.order_id
         AND a.attempt_number = v_expired.attempt_number
    ) THEN
      INSERT INTO public.payment_attempts (
        payment_id, order_id, user_id, stripe_payment_intent_id,
        payment_provider, provider_payment_id,
        attempt_number, status, amount, amount_paise, currency,
        payment_method, error_message, gateway_metadata, created_at, updated_at
      )
      SELECT p.id, p.order_id, p.user_id,
             CASE WHEN coalesce(v_expired.payment_provider, v_provider) = 'stripe' THEN v_expired.provider_payment_id ELSE NULL END,
             coalesce(v_expired.payment_provider, v_provider),
             v_expired.provider_payment_id,
             v_expired.attempt_number, 'expired', p.amount, p.amount_paise, p.currency,
             p.payment_method, 'Payment retry reservation expired.', coalesce(p.gateway_metadata, '{}'::jsonb),
             v_expired.expires_at, now()
        FROM public.payments p
       WHERE p.id = v_payment_id;
    END IF;

    UPDATE public.payment_retry_reservations
       SET status = 'expired', released_at = coalesce(released_at, now())
     WHERE id = v_expired.id;
  END LOOP;

  SELECT r.id, r.attempt_number
    INTO v_existing, v_existing_attempt
    FROM public.payment_retry_reservations r
   WHERE r.order_id = p_order_id
     AND r.user_id = p_user_id
     AND r.payment_provider = v_provider
     AND r.provider_payment_id = p_provider_payment_id
     AND r.status = 'reserved'
     AND r.expires_at > now()
   ORDER BY r.created_at DESC
   LIMIT 1
   FOR UPDATE;

  IF v_existing IS NOT NULL THEN
    UPDATE public.payments
       SET attempt_number = greatest(coalesce(attempt_number, 0), v_existing_attempt),
           total_attempts = greatest(coalesce(total_attempts, 0), v_existing_attempt),
           latest_attempt_number = greatest(coalesce(latest_attempt_number, 0), v_existing_attempt),
           max_attempts = v_policy_max,
           latest_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE latest_payment_intent_id END,
           provider_payment_id = p_provider_payment_id,
           payment_provider = v_provider,
           last_attempt_at = now(),
           updated_at = now()
     WHERE id = v_payment_id;
    RETURN QUERY SELECT v_existing, v_existing_attempt;
    RETURN;
  END IF;

  SELECT greatest(
    coalesce((SELECT max(a.attempt_number) FROM public.payment_attempts a WHERE a.order_id = p_order_id), 0),
    coalesce((SELECT max(r.attempt_number) FROM public.payment_retry_reservations r WHERE r.order_id = p_order_id), 0)
  ) + 1
    INTO v_next;

  IF v_next > v_policy_max THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%', v_policy_max USING errcode = 'P0001';
  END IF;

  INSERT INTO public.payment_retry_reservations (
    order_id, user_id, stripe_payment_intent_id,
    payment_provider, provider_payment_id,
    attempt_number, status, created_at, expires_at
  ) VALUES (
    p_order_id,
    p_user_id,
    CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE NULL END,
    v_provider,
    p_provider_payment_id,
    v_next,
    'reserved',
    now(),
    now() + make_interval(secs => v_policy_window)
  )
  RETURNING id INTO v_id;

  UPDATE public.payments
     SET attempt_number = v_next,
         total_attempts = v_next,
         latest_attempt_number = v_next,
         max_attempts = v_policy_max,
         latest_payment_intent_id = CASE WHEN v_provider = 'stripe' THEN p_provider_payment_id ELSE latest_payment_intent_id END,
         provider_payment_id = p_provider_payment_id,
         payment_provider = v_provider,
         last_attempt_at = now(),
         updated_at = now()
   WHERE id = v_payment_id;

  RETURN QUERY SELECT v_id, v_next;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.reserve_payment_retry_provider(uuid, uuid, text, text, integer, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry_provider(uuid, uuid, text, text, integer, integer)
  TO service_role;

CREATE OR REPLACE FUNCTION public.claim_webhook_event_provider(
  p_event_id text,
  p_event_type text,
  p_provider text,
  p_provider_payment_id text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  claimed boolean;
  provider text := lower(nullif(trim(p_provider), ''));
BEGIN
  IF nullif(trim(p_event_id), '') IS NULL OR provider IS NULL THEN
    RAISE EXCEPTION 'WEBHOOK_IDENTITY_INVALID';
  END IF;

  INSERT INTO public.webhook_events_ledger (
    event_id,
    event_type,
    stripe_payment_intent_id,
    payment_provider,
    provider_payment_id,
    status
  )
  VALUES (
    p_event_id,
    p_event_type,
    CASE WHEN provider = 'stripe' THEN p_provider_payment_id ELSE NULL END,
    provider,
    nullif(trim(p_provider_payment_id), ''),
    'pending'
  )
  ON CONFLICT (event_id) DO UPDATE
     SET event_type = excluded.event_type,
         payment_provider = excluded.payment_provider,
         provider_payment_id = excluded.provider_payment_id,
         stripe_payment_intent_id = CASE
           WHEN excluded.payment_provider = 'stripe' THEN excluded.provider_payment_id
           ELSE public.webhook_events_ledger.stripe_payment_intent_id
         END,
         status = 'pending',
         processed_at = null
   WHERE public.webhook_events_ledger.status <> 'processed'
  RETURNING true INTO claimed;

  RETURN coalesce(claimed, false);
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.claim_webhook_event_provider(text, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_webhook_event_provider(text, text, text, text)
  TO service_role;

CREATE INDEX IF NOT EXISTS payment_attempts_provider_attempt_idx
  ON public.payment_attempts(payment_provider, provider_payment_id, attempt_number, created_at DESC)
  WHERE provider_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_retry_provider_attempt_idx
  ON public.payment_retry_reservations(payment_provider, provider_payment_id, attempt_number, created_at DESC)
  WHERE provider_payment_id IS NOT NULL;
