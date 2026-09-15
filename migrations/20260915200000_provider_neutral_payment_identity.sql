-- Provider-neutral payment identity.
-- Legacy Stripe columns remain for backward compatibility and existing historical data.

ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS payment_provider text,
  ADD COLUMN IF NOT EXISTS provider_payment_id text;

ALTER TABLE public.payments
  ADD COLUMN IF NOT EXISTS payment_provider text,
  ADD COLUMN IF NOT EXISTS provider_payment_id text;

ALTER TABLE public.payment_attempts
  ADD COLUMN IF NOT EXISTS payment_provider text,
  ADD COLUMN IF NOT EXISTS provider_payment_id text;

ALTER TABLE public.payment_retry_reservations
  ADD COLUMN IF NOT EXISTS payment_provider text,
  ADD COLUMN IF NOT EXISTS provider_payment_id text;

ALTER TABLE public.webhook_events
  ADD COLUMN IF NOT EXISTS payment_provider text,
  ADD COLUMN IF NOT EXISTS provider_payment_id text;

UPDATE public.orders
SET payment_provider = 'stripe', provider_payment_id = stripe_payment_intent
WHERE payment_provider IS NULL
  AND stripe_payment_intent IS NOT NULL;

UPDATE public.payments
SET payment_provider = 'stripe', provider_payment_id = stripe_payment_intent_id
WHERE payment_provider IS NULL
  AND stripe_payment_intent_id IS NOT NULL;

UPDATE public.payment_attempts
SET payment_provider = 'stripe', provider_payment_id = stripe_payment_intent_id
WHERE payment_provider IS NULL
  AND stripe_payment_intent_id IS NOT NULL;

UPDATE public.payment_retry_reservations
SET payment_provider = 'stripe', provider_payment_id = stripe_payment_intent_id
WHERE payment_provider IS NULL
  AND stripe_payment_intent_id IS NOT NULL;

UPDATE public.webhook_events
SET payment_provider = 'stripe', provider_payment_id = stripe_payment_intent_id
WHERE payment_provider IS NULL
  AND stripe_payment_intent_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS payments_provider_payment_id_uq
  ON public.payments(payment_provider, provider_payment_id)
  WHERE payment_provider IS NOT NULL AND provider_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS orders_provider_payment_id_idx
  ON public.orders(payment_provider, provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_attempts_provider_payment_id_idx
  ON public.payment_attempts(payment_provider, provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS payment_retry_provider_payment_id_idx
  ON public.payment_retry_reservations(payment_provider, provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS webhook_events_provider_payment_id_idx
  ON public.webhook_events(payment_provider, provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

-- Provider-neutral atomic checkout/order creation. The previous Stripe-only RPC
-- remains untouched for backward compatibility; new code uses this function.
CREATE OR REPLACE FUNCTION public.create_pending_order_with_payment(
  p_order_data jsonb,
  p_items jsonb,
  p_ip_address text DEFAULT NULL,
  p_user_agent text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_order_id uuid;
  v_result jsonb;
  v_item jsonb;
  v_prod_id uuid;
  v_qty int;
  v_merged_item jsonb;
  v_total_amount numeric;
  v_amount_paise bigint;
  v_currency text;
  v_customer_id uuid;
  v_provider text;
  v_provider_payment_id text;
BEGIN
  v_provider := lower(nullif(trim(p_order_data->>'payment_provider'), ''));
  v_provider_payment_id := nullif(trim(p_order_data->>'provider_payment_id'), '');
  v_customer_id := (p_order_data->>'customer_id')::uuid;
  v_total_amount := (p_order_data->>'total_amount')::numeric;
  v_amount_paise := round(v_total_amount * 100)::bigint;
  v_currency := upper(coalesce(nullif(trim(p_order_data->>'currency'), ''), 'INR'));

  IF v_customer_id IS NULL
     OR v_provider IS NULL
     OR v_provider_payment_id IS NULL
     OR v_total_amount IS NULL
     OR v_total_amount < 0 THEN
    RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
  END IF;

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_prod_id := (v_item->>'product_id')::uuid;
    v_qty := (v_item->>'quantity')::int;

    UPDATE public.products
       SET stock = stock - v_qty
     WHERE id = v_prod_id
       AND stock >= v_qty;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'Inventory depleted for product_id: %', v_prod_id;
    END IF;
  END LOOP;

  v_order_id := gen_random_uuid();

  p_order_data := p_order_data || jsonb_build_object(
    'id', v_order_id,
    'tax_type', coalesce(p_order_data->>'tax_type', 'IGST'),
    'created_at', coalesce(p_order_data->>'created_at', now()::text),
    'updated_at', now()::text
  );

  INSERT INTO public.orders
  SELECT * FROM jsonb_populate_record(NULL::public.orders, p_order_data);

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
    attempt_number,
    total_attempts,
    latest_attempt_number,
    successful_attempt_number,
    latest_payment_intent_id,
    max_attempts,
    ip_address,
    user_agent,
    created_at,
    updated_at
  ) VALUES (
    v_order_id,
    v_customer_id,
    CASE WHEN v_provider = 'stripe' THEN v_provider_payment_id ELSE NULL END,
    v_provider,
    v_provider_payment_id,
    v_total_amount,
    v_amount_paise,
    v_currency,
    'requires_payment_method',
    NULL,
    0,
    NULL,
    NULL,
    CASE WHEN v_provider = 'stripe' THEN v_provider_payment_id ELSE NULL END,
    5,
    nullif(trim(p_ip_address), ''),
    nullif(trim(p_user_agent), ''),
    now(),
    now()
  );

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_merged_item := v_item || jsonb_build_object(
      'id', gen_random_uuid(),
      'order_id', v_order_id,
      'created_at', now()::text
    );

    INSERT INTO public.order_items
    SELECT * FROM jsonb_populate_record(NULL::public.order_items, v_merged_item);
  END LOOP;

  DELETE FROM public.cart_items
   WHERE cart_id IN (SELECT id FROM public.carts WHERE user_id = v_customer_id);

  UPDATE public.carts SET updated_at = now() WHERE user_id = v_customer_id;

  SELECT row_to_json(o)::jsonb INTO v_result
    FROM public.orders o
   WHERE o.id = v_order_id;

  RETURN v_result;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  TO service_role;

-- Provider-neutral atomic settlement. The existing Stripe-specific settlement RPC
-- is retained for old clients and historical replay paths.
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
