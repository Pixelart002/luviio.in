-- Fail closed on payment settlement integrity mismatches.
-- The settlement RPC must never return a normal success-path status when
-- provider amount/currency/PI/order binding does not match the order.
-- ALREADY_PAID and ORDER_ALREADY_CANCELLED remain explicit idempotent states.

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
    p_order_id uuid,
    p_pi_id text,
    p_amount numeric,
    p_user_id uuid,
    p_payment_method text DEFAULT NULL,
    p_stripe_currency text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
    v_order public.orders%ROWTYPE;
    v_payment_order_id uuid;
    v_payment_user_id uuid;
    v_order_currency text;
BEGIN
    SELECT * INTO v_order
      FROM public.orders
     WHERE id = p_order_id
       AND customer_id = p_user_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'PAYMENT_ORDER_NOT_FOUND';
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
       OR ROUND(p_amount, 2) <> ROUND(v_order.total_amount, 2) THEN
        RAISE EXCEPTION 'PAYMENT_AMOUNT_MISMATCH';
    END IF;

    v_order_currency := COALESCE(UPPER(TRIM(v_order.currency)), '');
    IF v_order_currency <> 'INR' THEN
        RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
    END IF;

    IF p_stripe_currency IS NULL
       OR UPPER(TRIM(p_stripe_currency)) <> v_order_currency THEN
        RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
    END IF;

    IF v_order.stripe_payment_intent IS NOT NULL
       AND v_order.stripe_payment_intent <> p_pi_id THEN
        RAISE EXCEPTION 'PAYMENT_INTENT_MISMATCH';
    END IF;

    SELECT order_id, user_id
      INTO v_payment_order_id, v_payment_user_id
      FROM public.payments
     WHERE stripe_payment_intent_id = p_pi_id
     LIMIT 1;

    IF FOUND
       AND (v_payment_order_id <> p_order_id OR v_payment_user_id <> p_user_id) THEN
        RAISE EXCEPTION 'PAYMENT_BINDING_MISMATCH';
    END IF;

    INSERT INTO public.payments (
        order_id,
        user_id,
        stripe_payment_intent_id,
        amount,
        currency,
        status,
        payment_method
    ) VALUES (
        p_order_id,
        p_user_id,
        p_pi_id,
        p_amount,
        v_order_currency,
        'succeeded',
        p_payment_method
    )
    ON CONFLICT (stripe_payment_intent_id) DO UPDATE SET
        order_id = EXCLUDED.order_id,
        user_id = EXCLUDED.user_id,
        amount = EXCLUDED.amount,
        currency = EXCLUDED.currency,
        status = 'succeeded',
        payment_method = COALESCE(EXCLUDED.payment_method, public.payments.payment_method);

    UPDATE public.orders
       SET status = 'paid',
           stripe_payment_intent = p_pi_id,
           paid_at = COALESCE(paid_at, NOW())
     WHERE id = p_order_id;

    RETURN 'SETTLED';
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text, text) TO service_role;
