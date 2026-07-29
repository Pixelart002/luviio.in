-- Fix: settle_order_transaction used bare `user_id` column reference which does
-- not exist. The function now correctly uses the input parameter `p_user_id`
-- throughout, and filters orders by the `customer_id` column (the actual FK).
--
-- Apply via: Supabase Dashboard → SQL Editor, or `supabase db push`.

CREATE OR REPLACE FUNCTION public.settle_order_transaction(
    p_order_id  uuid,
    p_pi_id     text,
    p_amount    numeric,
    p_user_id   uuid
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_status text;
BEGIN
    -- Lock the order row to prevent concurrent settlement
    SELECT status
      INTO v_current_status
      FROM public.orders
     WHERE id          = p_order_id
       AND customer_id = p_user_id   -- was incorrectly written as `user_id`
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found for user %', p_order_id, p_user_id;
    END IF;

    -- Idempotency guard: already settled
    IF v_current_status = 'paid' THEN
        RETURN 'ALREADY_PAID';
    END IF;

    -- Mark order as paid
    UPDATE public.orders
       SET status                = 'paid',
           stripe_payment_intent = p_pi_id
     WHERE id = p_order_id;

    -- Record payment
    INSERT INTO public.payments (
        order_id,
        stripe_payment_intent_id,
        amount,
        currency,
        status,
        payment_method
    ) VALUES (
        p_order_id,
        p_pi_id,
        p_amount,
        'INR',
        'succeeded',
        'card'
    )
    ON CONFLICT (stripe_payment_intent_id) DO NOTHING;

    RETURN 'SETTLED';
END;
$$;