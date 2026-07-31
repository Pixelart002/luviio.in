-- Migration: Add cancel_order_and_release_stock RPC function
-- Cancels a pending order and atomically restores stock for all its items.
-- Only operates on orders in a cancellable state (pending, paid, processing).

CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(p_order_id uuid)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_status text;
    v_item           record;
    v_stock_after    integer;
BEGIN
    -- Lock the order row to prevent concurrent modifications
    SELECT status
      INTO v_current_status
      FROM public.orders
     WHERE id = p_order_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found', p_order_id;
    END IF;

    -- Idempotency guard: already cancelled
    IF v_current_status = 'cancelled' THEN
        RETURN 'ALREADY_CANCELLED';
    END IF;

    -- Safety guard: do not cancel terminal/non-cancellable orders
    IF v_current_status IN ('shipped', 'delivered', 'refunded') THEN
        RAISE EXCEPTION 'Cannot cancel order % in status %', p_order_id, v_current_status;
    END IF;

    -- Mark order as cancelled
    UPDATE public.orders
       SET status = 'cancelled'
     WHERE id = p_order_id;

    -- Restore stock for each item and write audit rows
    FOR v_item IN
        SELECT oi.product_id, oi.quantity, p.sku, p.stock
          FROM public.order_items oi
          JOIN public.products p ON p.id = oi.product_id
         WHERE oi.order_id = p_order_id
    LOOP
        v_stock_after := v_item.stock + v_item.quantity;

        UPDATE public.products
           SET stock = v_stock_after
         WHERE id = v_item.product_id;

        INSERT INTO public.stock_audit (product_id, sku, delta, stock_after, reason)
        VALUES (
            v_item.product_id,
            v_item.sku,
            v_item.quantity,          -- positive delta = stock restored
            v_stock_after,
            'order_cancelled:' || p_order_id::text
        );
    END LOOP;

    RETURN 'CANCELLED';
END;
$$;