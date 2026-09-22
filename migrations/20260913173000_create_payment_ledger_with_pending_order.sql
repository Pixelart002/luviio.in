-- Payment lifecycle invariant:
-- every Stripe-backed pending order must have exactly one canonical payments row
-- before payment_attempts / retry reservation RPCs are called.
--
-- Previously create_pending_order_with_reservation created the order and order_items
-- but not public.payments. The service then called record_payment_attempt(), which
-- correctly failed closed with PAYMENT_RECORD_NOT_FOUND. That left a live Stripe
-- PaymentIntent attached to an order with no payment ledger and made retry impossible.

CREATE OR REPLACE FUNCTION public.create_pending_order_with_reservation(
  p_order_data jsonb,
  p_items jsonb
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
  v_payment_intent_id text;
BEGIN
  -- Reserve inventory atomically. Any failure aborts the whole transaction.
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
    'tax_type', COALESCE(p_order_data->>'tax_type', 'IGST'),
    'created_at', COALESCE(p_order_data->>'created_at', NOW()::text),
    'updated_at', NOW()::text
  );

  INSERT INTO public.orders
  SELECT * FROM jsonb_populate_record(NULL::public.orders, p_order_data);

  -- Establish the canonical payment aggregate in the SAME transaction as the
  -- order. total_attempts is zero here because the service records attempt #1
  -- immediately after this RPC succeeds; payment_attempts remains the durable
  -- attempt history and record_payment_attempt() remains the accounting authority.
  v_customer_id := (p_order_data->>'customer_id')::uuid;
  v_payment_intent_id := NULLIF(TRIM(p_order_data->>'stripe_payment_intent'), '');
  v_total_amount := (p_order_data->>'total_amount')::numeric;
  v_amount_paise := ROUND(v_total_amount * 100)::bigint;
  v_currency := UPPER(COALESCE(NULLIF(TRIM(p_order_data->>'currency'), ''), 'INR'));

  IF v_customer_id IS NULL OR v_payment_intent_id IS NULL OR v_total_amount IS NULL OR v_total_amount < 0 THEN
    RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
  END IF;

  INSERT INTO public.payments (
    order_id,
    user_id,
    stripe_payment_intent_id,
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
    created_at,
    updated_at
  ) VALUES (
    v_order_id,
    v_customer_id,
    v_payment_intent_id,
    v_total_amount,
    v_amount_paise,
    v_currency,
    'requires_payment_method',
    NULL,
    0,
    NULL,
    NULL,
    v_payment_intent_id,
    5,
    NOW(),
    NOW()
  );

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_merged_item := v_item || jsonb_build_object(
      'id', gen_random_uuid(),
      'order_id', v_order_id,
      'created_at', NOW()::text
    );

    INSERT INTO public.order_items
    SELECT * FROM jsonb_populate_record(NULL::public.order_items, v_merged_item);
  END LOOP;

  -- Consume the source cart in the SAME transaction as order + payment ledger.
  DELETE FROM public.cart_items
   WHERE cart_id IN (
     SELECT id
       FROM public.carts
      WHERE user_id = v_customer_id
   );

  UPDATE public.carts
     SET updated_at = NOW()
   WHERE user_id = v_customer_id;

  SELECT row_to_json(o)::jsonb
    INTO v_result
    FROM public.orders o
   WHERE o.id = v_order_id;

  RETURN v_result;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
  TO service_role;
