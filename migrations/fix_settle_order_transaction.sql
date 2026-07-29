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
        user_id,
        stripe_payment_intent_id,
        amount,
        amount_paise,
        currency,
        status,
        payment_method
    ) VALUES (
        p_order_id,
        p_user_id,
        p_pi_id,
        p_amount,
        ROUND(p_amount*100),
        'INR',
        'succeeded',
        'card'
    )
    ON CONFLICT (stripe_payment_intent_id) DO NOTHING;

    RETURN 'SETTLED';
END;