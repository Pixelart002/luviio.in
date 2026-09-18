-- Customer cancellation releases reserved stock but does not recreate cart items.
-- The cart was consumed when checkout created the order; cancellation ends the
-- order and intentionally leaves the cart unchanged.

-- Allow customer cancellation of paid/processing COD orders without a Stripe refund.
-- Stripe paid/processing orders remain refund-only at the database boundary.

CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(
    p_order_id uuid,
    p_reason text DEFAULT 'order_cancelled'::text,
    p_target_status text DEFAULT 'cancelled'::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_status text;
    v_customer_id uuid;
    v_payment_method text;
    v_payment_provider text;
    v_cart_id uuid;
    v_item record;
    v_final_status text;
BEGIN
    SELECT
        lower(status),
        customer_id,
        lower(coalesce(payment_method, '')),
        lower(coalesce(payment_provider, ''))
      INTO
        v_status,
        v_customer_id,
        v_payment_method,
        v_payment_provider
      FROM public.orders
     WHERE id = p_order_id
     FOR UPDATE;

    IF v_status IS NULL THEN
        RETURN 'ORDER_NOT_FOUND';
    END IF;

    IF v_status IN ('cancelled', 'refunded') THEN
        RETURN 'ALREADY_CANCELLED';
    END IF;

    IF v_status IN ('shipped', 'delivered') THEN
        RETURN 'ORDER_ALREADY_FULFILLED';
    END IF;

    IF v_status = 'pending' THEN
        v_final_status := 'cancelled';
    ELSIF v_status IN ('paid', 'processing')
      AND lower(btrim(coalesce(p_target_status, ''))) = 'refunded' THEN
        v_final_status := 'refunded';
    ELSIF v_status IN ('paid', 'processing')
      AND lower(btrim(coalesce(p_target_status, ''))) = 'cancelled'
      AND (v_payment_method = 'cod' OR v_payment_provider = 'cod') THEN
        v_final_status := 'cancelled';
    ELSE
        RETURN 'INVALID_TARGET_STATUS';
    END IF;

    PERFORM set_config('app.inventory_activity_type', 'sale_released', true);
    PERFORM set_config(
        'app.inventory_reason',
        COALESCE(NULLIF(BTRIM(p_reason), ''), 'order_cancelled'),
        true
    );
    PERFORM set_config('app.inventory_reference_type', 'order', true);
    PERFORM set_config('app.inventory_reference_id', p_order_id::text, true);
    PERFORM set_config(
        'app.inventory_metadata',
        jsonb_build_object(
            'source', 'cancel_order_and_release_stock',
            'target_status', v_final_status
        )::text,
        true
    );

    FOR v_item IN
        SELECT product_id, quantity
          FROM public.order_items
         WHERE order_id = p_order_id
           AND product_id IS NOT NULL
    LOOP
        UPDATE public.products
           SET stock = COALESCE(stock, 0) + v_item.quantity
         WHERE id = v_item.product_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'PRODUCT_NOT_FOUND:%', v_item.product_id;
        END IF;
    END LOOP;

    PERFORM public.release_coupon_reservation(p_order_id);

    UPDATE public.orders
       SET status = v_final_status,
           notes = COALESCE(notes, '') || ' | Cancel Reason: ' ||
                   COALESCE(NULLIF(BTRIM(p_reason), ''), 'order_cancelled'),
           cancelled_at = NOW(),
           updated_at = NOW()
     WHERE id = p_order_id;

    RETURN upper(v_final_status);
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text, text)
    TO service_role;
