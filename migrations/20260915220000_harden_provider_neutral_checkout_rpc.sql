-- Harden the provider-neutral checkout RPC against malformed or hostile cart payloads.
-- This function is service_role-only, but input validation is still mandatory.

CREATE OR REPLACE FUNCTION public.create_pending_order_with_payment(
  p_order_data jsonb,
  p_items jsonb,
  p_ip_address text DEFAULT NULL,
  p_user_agent text DEFAULT NULL
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, pg_temp
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
  v_product_active boolean;
BEGIN
  IF jsonb_typeof(p_order_data) <> 'object'
     OR jsonb_typeof(p_items) <> 'array'
     OR jsonb_array_length(p_items) = 0 THEN
    RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
  END IF;

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
     OR v_total_amount <= 0
     OR v_amount_paise <= 0
     OR v_currency <> 'INR' THEN
    RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
  END IF;

  -- Validate every item before mutating inventory. A quantity must be a
  -- positive integer and the product must be active and sufficiently stocked.
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    BEGIN
      v_prod_id := (v_item->>'product_id')::uuid;
      v_qty := (v_item->>'quantity')::int;
    EXCEPTION WHEN invalid_text_representation THEN
      RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
    END;

    IF v_prod_id IS NULL OR v_qty IS NULL OR v_qty <= 0 OR v_qty > 100 THEN
      RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
    END IF;

    SELECT is_active INTO v_product_active
      FROM public.products
     WHERE id = v_prod_id
     FOR UPDATE;

    IF NOT FOUND OR coalesce(v_product_active, false) = false THEN
      RAISE EXCEPTION 'Product unavailable for checkout: %', v_prod_id;
    END IF;

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

  UPDATE public.carts
     SET updated_at = now()
   WHERE user_id = v_customer_id;

  SELECT row_to_json(o)::jsonb
    INTO v_result
    FROM public.orders o
   WHERE o.id = v_order_id;

  RETURN v_result;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_payment(jsonb, jsonb, text, text)
  TO service_role;
