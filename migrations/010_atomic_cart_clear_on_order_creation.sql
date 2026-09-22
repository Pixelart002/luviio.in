-- Enforce the checkout invariant at the database transaction boundary:
-- a successfully created order with reserved inventory consumes the source cart
-- in the same transaction. This prevents order-created/cart-not-cleared splits.

CREATE OR REPLACE FUNCTION public.create_pending_order_with_reservation(p_order_data jsonb, p_items jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $function$
DECLARE
  v_order_id uuid;
  v_result jsonb;
  v_item jsonb;
  v_prod_id uuid;
  v_qty int;
  v_merged_item jsonb;
BEGIN
  -- Reserve inventory atomically. Any failure aborts the whole transaction.
  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_prod_id := (v_item->>'product_id')::uuid;
    v_qty := (v_item->>'quantity')::int;

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
    'tax_type', COALESCE(p_order_data->>'tax_type', 'IGST'),
    'created_at', COALESCE(p_order_data->>'created_at', NOW()::text),
    'updated_at', NOW()::text
  );

  INSERT INTO public.orders
  SELECT * FROM jsonb_populate_record(NULL::public.orders, p_order_data);

  FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
  LOOP
    v_merged_item := v_item || jsonb_build_object(
      'id', gen_random_uuid(),
      'order_id', v_order_id,
      'created_at', NOW()::text
    );

    INSERT INTO public.order_items
    SELECT * FROM jsonb_populate_record(NULL::public.order_items, v_merged_item);
  END LOOP;

  -- Checkout invariant: after the order and its inventory reservation succeed,
  -- consume the customer's source cart in this SAME database transaction.
  -- The backend's best-effort cart cleanup remains harmless/idempotent because
  -- this DELETE has already made the cart empty before the response is returned.
  DELETE FROM public.cart_items
   WHERE cart_id IN (
     SELECT id
       FROM public.carts
      WHERE user_id = (p_order_data->>'customer_id')::uuid
   );

  UPDATE public.carts
     SET updated_at = NOW()
   WHERE user_id = (p_order_data->>'customer_id')::uuid;

  SELECT row_to_json(o)::jsonb
    INTO v_result
    FROM public.orders o
   WHERE o.id = v_order_id;

  RETURN v_result;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
  TO service_role;
