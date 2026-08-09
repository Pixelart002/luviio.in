-- ============================================================
-- Fix: cancel_order_and_release_stock() only blocked cancelling
-- orders already in 'cancelled'/'refunded' state -- it did NOT
-- block 'shipped' or 'delivered' orders. If this RPC is ever
-- called on a shipped/delivered order (accidental retry, a bug
-- in a caller, admin misclick), it would cancel it AND add the
-- stock back, even though the physical product already left the
-- warehouse -- a real inventory-accuracy bug.
--
-- Safe to re-run (CREATE OR REPLACE).
-- ============================================================

CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(
    p_order_id uuid,
    p_reason text DEFAULT 'order_cancelled'::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
DECLARE
    v_status TEXT;
    v_item RECORD;
BEGIN
    SELECT status INTO v_status FROM public.orders WHERE id = p_order_id FOR UPDATE;

    IF v_status IN ('cancelled', 'refunded') THEN
        RETURN 'ALREADY_CANCELLED';
    END IF;

    -- 🔥 FIX: also refuse to touch orders that have already shipped/delivered --
    -- cancelling + restoring stock on those would be factually wrong (the
    -- physical goods are already out the door).
    IF v_status IN ('shipped', 'delivered') THEN
        RETURN 'ORDER_ALREADY_FULFILLED';
    END IF;

    -- Restore Stock
    FOR v_item IN SELECT product_id, quantity FROM public.order_items WHERE order_id = p_order_id LOOP
        UPDATE public.products SET stock = stock + v_item.quantity WHERE id = v_item.product_id;
    END LOOP;

    -- Mark Cancelled
    UPDATE public.orders
       SET status = 'cancelled',
           notes = COALESCE(notes, '') || ' | Cancel Reason: ' || p_reason,
           cancelled_at = NOW(),
           updated_at = NOW()
     WHERE id = p_order_id;

    RETURN 'CANCELLED';
END;
$function$;