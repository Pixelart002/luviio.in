BEGIN;

-- Repair provider-neutral settlement so accounting evidence exists before paid status.
CREATE OR REPLACE FUNCTION public.settle_payment_transaction(
  p_order_id uuid,
  p_provider text,
  p_provider_payment_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL,
  p_currency text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_existing_order_id uuid;
  v_existing_user_id uuid;
  v_order_currency text;
  v_payment_id uuid;
  v_attempt integer;
BEGIN
  p_provider := lower(nullif(trim(p_provider), ''));
  p_provider_payment_id := nullif(trim(p_provider_payment_id), '');

  IF p_provider IS NULL OR p_provider_payment_id IS NULL THEN
    RETURN 'PAYMENT_IDENTITY_INVALID';
  END IF;

  SELECT * INTO v_order
    FROM public.orders
   WHERE id = p_order_id
     AND customer_id = p_user_id
   FOR UPDATE;

  IF NOT FOUND THEN
    RETURN 'ORDER_NOT_FOUND';
  END IF;

  IF v_order.status = 'paid' THEN
    RETURN 'ALREADY_PAID';
  END IF;

  IF v_order.status = 'cancelled' THEN
    RETURN 'ORDER_ALREADY_CANCELLED';
  END IF;

  IF p_amount IS NULL
     OR p_amount <= 0
     OR v_order.total_amount IS NULL
     OR round(p_amount, 2) <> round(v_order.total_amount, 2) THEN
    RETURN 'PAYMENT_AMOUNT_MISMATCH';
  END IF;

  v_order_currency := coalesce(upper(trim(v_order.currency)), '');
  IF v_order_currency = '' OR p_currency IS NULL OR upper(trim(p_currency)) <> v_order_currency THEN
    RETURN 'PAYMENT_CURRENCY_MISMATCH';
  END IF;

  IF v_order.payment_provider IS NOT NULL
     AND lower(v_order.payment_provider) <> p_provider THEN
    RETURN 'PAYMENT_PROVIDER_MISMATCH';
  END IF;

  IF v_order.provider_payment_id IS NOT NULL
     AND v_order.provider_payment_id <> p_provider_payment_id THEN
    RETURN 'PAYMENT_INTENT_MISMATCH';
  END IF;

  SELECT order_id, user_id
    INTO v_existing_order_id, v_existing_user_id
    FROM public.payments
   WHERE payment_provider = p_provider
     AND provider_payment_id = p_provider_payment_id
   LIMIT 1;

  IF FOUND
     AND (v_existing_order_id <> p_order_id OR v_existing_user_id <> p_user_id) THEN
    RETURN 'PAYMENT_BINDING_MISMATCH';
  END IF;

  INSERT INTO public.payments (
    order_id,
    user_id,
    stripe_payment_intent_id,
    payment_provider,
    provider_payment_id,
    amount,
    amount_paise,
    currency,
    status,
    payment_method,
    updated_at
  ) VALUES (
    p_order_id,
    p_user_id,
    CASE WHEN p_provider = 'stripe' THEN p_provider_payment_id ELSE NULL END,
    p_provider,
    p_provider_payment_id,
    p_amount,
    round(p_amount * 100)::bigint,
    v_order_currency,
    'succeeded',
    p_payment_method,
    now()
  )
  ON CONFLICT (payment_provider, provider_payment_id) DO UPDATE SET
    order_id = excluded.order_id,
    user_id = excluded.user_id,
    amount = excluded.amount,
    amount_paise = excluded.amount_paise,
    currency = excluded.currency,
    status = 'succeeded',
    payment_method = coalesce(excluded.payment_method, public.payments.payment_method),
    updated_at = now();

  SELECT p.id, COALESCE(p.successful_attempt_number, p.latest_attempt_number, p.attempt_number, 1)
    INTO v_payment_id, v_attempt
    FROM public.payments p
   WHERE p.order_id = p_order_id
     AND p.payment_provider = p_provider
     AND p.provider_payment_id = p_provider_payment_id
   ORDER BY p.created_at DESC
   LIMIT 1
   FOR UPDATE;

  IF v_payment_id IS NULL THEN
    RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND';
  END IF;

  INSERT INTO public.payment_ledger (
    order_id, payment_id, provider, provider_payment_id, entry_type, direction,
    amount, amount_paise, currency, attempt_number, reference, metadata
  ) VALUES (
    p_order_id, v_payment_id, p_provider, p_provider_payment_id,
    'payment_received', 'credit', p_amount, round(p_amount * 100)::bigint,
    v_order_currency, v_attempt, p_provider_payment_id,
    jsonb_build_object('source', 'provider_neutral_payment_settlement',
                       'payment_method', p_payment_method)
  )
  ON CONFLICT (provider, provider_payment_id, entry_type) DO NOTHING;

  UPDATE public.orders
     SET status = 'paid',
         payment_provider = p_provider,
         provider_payment_id = p_provider_payment_id,
         stripe_payment_intent = CASE
           WHEN p_provider = 'stripe' THEN p_provider_payment_id
           ELSE stripe_payment_intent
         END,
         paid_at = coalesce(paid_at, now())
   WHERE id = p_order_id;

  RETURN 'SETTLED';
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.settle_payment_transaction(uuid, text, text, numeric, uuid, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.settle_payment_transaction(uuid, text, text, numeric, uuid, text, text)
  TO service_role;

COMMIT;
