-- Restore reserved checkout items to the customer's active cart when a pending
-- checkout is cancelled. Checkout creation clears cart_items atomically, so a
-- customer cancellation must put those items back before another payment method
-- can be selected.

CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(
    p_order_id uuid,
    p_reason text DEFAULT 'order_cancelled'::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $function$
DECLARE
    v_status text;
    v_customer_id uuid;
    v_cart_id uuid;
    v_item record;
BEGIN
    SELECT status, customer_id
      INTO v_status, v_customer_id
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

    -- Restore reserved stock exactly once inside the same transaction.
    FOR v_item IN
        SELECT product_id, quantity
          FROM public.order_items
         WHERE order_id = p_order_id
    LOOP
        UPDATE public.products
           SET stock = stock + v_item.quantity
         WHERE id = v_item.product_id;
    END LOOP;

    -- Re-create the customer's active cart. Checkout creation intentionally
    -- emptied it, so cancellation must restore the original order items.
    IF v_customer_id IS NOT NULL THEN
        INSERT INTO public.carts (user_id, created_at, updated_at)
        VALUES (v_customer_id, NOW(), NOW())
        ON CONFLICT (user_id) DO NOTHING;

        SELECT id
          INTO v_cart_id
          FROM public.carts
         WHERE user_id = v_customer_id
         FOR UPDATE;

        FOR v_item IN
            SELECT product_id, unit_price, quantity
              FROM public.order_items
             WHERE order_id = p_order_id
               AND product_id IS NOT NULL
        LOOP
            INSERT INTO public.cart_items (
                cart_id,
                product_id,
                quantity,
                price_snapshot,
                added_at
            )
            VALUES (
                v_cart_id,
                v_item.product_id,
                v_item.quantity,
                v_item.unit_price,
                NOW()
            )
            ON CONFLICT (cart_id, product_id)
            DO UPDATE SET
                quantity = LEAST(public.cart_items.quantity + EXCLUDED.quantity, 100),
                price_snapshot = EXCLUDED.price_snapshot,
                added_at = NOW();
        END LOOP;

        UPDATE public.carts
           SET updated_at = NOW()
         WHERE id = v_cart_id;
    END IF;

    PERFORM public.release_coupon_reservation(p_order_id);

    UPDATE public.orders
       SET status = 'cancelled',
           notes = COALESCE(notes, '') || ' | Cancel Reason: ' || p_reason,
           cancelled_at = NOW(),
           updated_at = NOW()
     WHERE id = p_order_id;

    RETURN 'CANCELLED';
END;
$function$;
