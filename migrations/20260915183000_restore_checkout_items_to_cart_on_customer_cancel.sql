-- Restore a cancelled customer checkout back into the customer's cart.
-- Stock/order cancellation and cart restoration happen in one transaction.

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
    v_existing_qty integer;
BEGIN
    SELECT o.status, o.customer_id
      INTO v_status, v_customer_id
      FROM public.orders o
     WHERE o.id = p_order_id
     FOR UPDATE;

    IF v_status IS NULL THEN
        RETURN 'NOT_FOUND';
    END IF;

    IF v_status IN ('cancelled', 'refunded') THEN
        RETURN 'ALREADY_CANCELLED';
    END IF;

    IF v_status IN ('shipped', 'delivered', 'paid', 'processing') THEN
        RETURN 'ORDER_ALREADY_FULFILLED';
    END IF;

    FOR v_item IN
        SELECT oi.product_id, oi.quantity, oi.unit_price
          FROM public.order_items oi
         WHERE oi.order_id = p_order_id
           AND oi.product_id IS NOT NULL
    LOOP
        UPDATE public.products p
           SET stock = p.stock + v_item.quantity
         WHERE p.id = v_item.product_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Product % no longer exists; checkout cancellation cannot restore inventory safely.', v_item.product_id;
        END IF;
    END LOOP;

    PERFORM public.release_coupon_reservation(p_order_id);

    IF p_reason = 'customer_requested' AND v_customer_id IS NOT NULL THEN
        INSERT INTO public.carts (user_id, created_at, updated_at)
        VALUES (v_customer_id, NOW(), NOW())
        ON CONFLICT (user_id) DO UPDATE SET updated_at = NOW()
        RETURNING id INTO v_cart_id;

        FOR v_item IN
            SELECT oi.product_id, oi.quantity, oi.unit_price
              FROM public.order_items oi
             WHERE oi.order_id = p_order_id
               AND oi.product_id IS NOT NULL
        LOOP
            SELECT ci.quantity
              INTO v_existing_qty
              FROM public.cart_items ci
             WHERE ci.cart_id = v_cart_id
               AND ci.product_id = v_item.product_id
             FOR UPDATE;

            IF v_existing_qty IS NULL THEN
                INSERT INTO public.cart_items (cart_id, product_id, quantity, price_snapshot, added_at)
                VALUES (v_cart_id, v_item.product_id, v_item.quantity, v_item.unit_price, NOW());
            ELSE
                IF v_existing_qty + v_item.quantity > 100 THEN
                    RAISE EXCEPTION 'Cart quantity limit would be exceeded for product %.', v_item.product_id;
                END IF;
                UPDATE public.cart_items
                   SET quantity = v_existing_qty + v_item.quantity,
                       price_snapshot = v_item.unit_price,
                       added_at = NOW()
                 WHERE cart_id = v_cart_id
                   AND product_id = v_item.product_id;
            END IF;
        END LOOP;

        UPDATE public.carts SET updated_at = NOW() WHERE id = v_cart_id;
    END IF;

    UPDATE public.orders
       SET status = 'cancelled',
           notes = COALESCE(notes, '') || ' | Cancel Reason: ' || p_reason,
           cancelled_at = NOW(),
           updated_at = NOW()
     WHERE id = p_order_id;

    RETURN 'CANCELLED';
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text) TO service_role;
