-- Coupon redemption consistency hardening.
--
-- The coupon is validated while the order is created, but the usage counter
-- must only be consumed at the authoritative success boundary. Online orders
-- can be settled by the Stripe webhook, so the settlement RPC owns the
-- redemption write and keeps it in the same transaction as marking the order
-- paid.

CREATE OR REPLACE FUNCTION public.record_coupon_redemption(
  p_coupon_id uuid,
  p_user_id uuid,
  p_order_id uuid,
  p_discount numeric
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_limit integer;
  v_used integer;
  v_per_user integer;
  v_user_used integer;
BEGIN
  -- Idempotent retry for the same order.
  IF EXISTS (
    SELECT 1
      FROM public.coupon_redemptions
     WHERE coupon_id = p_coupon_id
       AND user_id = p_user_id
       AND order_id = p_order_id
  ) THEN
    RETURN true;
  END IF;

  SELECT usage_limit, COALESCE(used_count, 0), COALESCE(per_user_limit, 1)
    INTO v_limit, v_used, v_per_user
    FROM public.coupons
   WHERE id = p_coupon_id AND is_active = true
   FOR UPDATE;

  IF NOT FOUND THEN RETURN false; END IF;
  IF v_limit IS NOT NULL AND v_used >= v_limit THEN RETURN false; END IF;

  SELECT count(*) INTO v_user_used
    FROM public.coupon_redemptions
   WHERE coupon_id = p_coupon_id AND user_id = p_user_id;
  IF v_user_used >= v_per_user THEN RETURN false; END IF;

  INSERT INTO public.coupon_redemptions (coupon_id, user_id, order_id, discount)
  VALUES (p_coupon_id, p_user_id, p_order_id, p_discount);

  UPDATE public.coupons
     SET used_count = v_used + 1, updated_at = now()
   WHERE id = p_coupon_id;
  RETURN true;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.record_coupon_redemption(uuid, uuid, uuid, numeric) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_coupon_redemption(uuid, uuid, uuid, numeric) TO service_role;

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
    p_order_id uuid,
    p_pi_id text,
    p_amount numeric,
    p_user_id uuid,
    p_payment_method text DEFAULT NULL::text,
    p_stripe_currency text DEFAULT NULL::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $$
DECLARE
    v_order public.orders%ROWTYPE;
    v_payment_order_id uuid;
    v_payment_user_id uuid;
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

    IF COALESCE(UPPER(TRIM(v_order.currency)), '') <> 'INR' THEN
        RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
    END IF;

    IF p_stripe_currency IS NULL
       OR UPPER(TRIM(p_stripe_currency)) <> UPPER(TRIM(v_order.currency)) THEN
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
        UPPER(TRIM(v_order.currency)),
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

    IF v_order.coupon_id IS NOT NULL THEN
        IF NOT public.record_coupon_redemption(
            v_order.coupon_id,
            p_user_id,
            p_order_id,
            COALESCE(v_order.discount_amount, 0)
        ) THEN
            RAISE EXCEPTION 'COUPON_REDEMPTION_FAILED';
        END IF;
    END IF;

    RETURN 'SETTLED';
END;
$$;

REVOKE EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text, text) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text, text) TO service_role;
