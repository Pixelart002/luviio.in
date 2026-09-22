-- Coupon lifecycle hardening: reserve per-user/global usage at order creation,
-- then convert reservation -> redeemed only at successful payment settlement.
-- Also provides an idempotent cleanup RPC for expired reservations.

CREATE OR REPLACE FUNCTION public.create_pending_order_with_reservation(
    p_order_data jsonb,
    p_items jsonb
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $$
DECLARE
    v_order_id uuid;
    v_result jsonb;
    v_item jsonb;
    v_merged_item jsonb;
    v_prod_id uuid;
    v_qty integer;
    v_total_amount numeric;
    v_amount_paise bigint;
    v_currency text;
    v_customer_id uuid;
    v_payment_intent_id text;
    v_payment_method text;
    v_coupon_id uuid;
    v_coupon_discount numeric;
    v_coupon_reserved boolean;
BEGIN
    v_order_id := gen_random_uuid();

    PERFORM set_config('app.inventory_activity_type','sale_reserved',true);
    PERFORM set_config('app.inventory_reason','checkout_stock_reservation',true);
    PERFORM set_config('app.inventory_reference_type','order',true);
    PERFORM set_config('app.inventory_reference_id',v_order_id::text,true);
    PERFORM set_config('app.inventory_metadata',jsonb_build_object('source','create_pending_order_with_reservation')::text,true);

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_prod_id := (v_item->>'product_id')::uuid;
        v_qty := (v_item->>'quantity')::integer;
        UPDATE public.products
           SET stock = stock - v_qty
         WHERE id = v_prod_id
           AND stock >= v_qty
           AND is_active = true;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Inventory depleted for product_id: %', v_prod_id;
        END IF;
    END LOOP;

    p_order_data := p_order_data || jsonb_build_object(
        'id', v_order_id,
        'tax_type', coalesce(p_order_data->>'tax_type','IGST'),
        'created_at', coalesce(p_order_data->>'created_at',now()::text),
        'updated_at', now()::text
    );

    INSERT INTO public.orders
    SELECT * FROM jsonb_populate_record(null::public.orders,p_order_data);

    v_customer_id := (p_order_data->>'customer_id')::uuid;
    v_payment_intent_id := nullif(trim(p_order_data->>'stripe_payment_intent'),'');
    v_total_amount := (p_order_data->>'total_amount')::numeric;
    v_amount_paise := round(v_total_amount * 100)::bigint;
    v_currency := upper(coalesce(nullif(trim(p_order_data->>'currency'),''),'INR'));
    v_payment_method := lower(coalesce(nullif(trim(p_order_data->>'payment_method'),''),'cod'));

    IF v_customer_id IS NULL OR v_total_amount IS NULL OR v_total_amount < 0 THEN
        RAISE EXCEPTION 'PAYMENT_LEDGER_DATA_INVALID';
    END IF;

    IF v_payment_intent_id IS NULL THEN
        INSERT INTO public.payments(
            order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
            payment_method,attempt_number,total_attempts,latest_attempt_number,successful_attempt_number,
            latest_payment_intent_id,max_attempts,created_at,updated_at
        ) VALUES (
            v_order_id,v_customer_id,null,v_total_amount,v_amount_paise,v_currency,'pending',
            'cod',null,0,null,null,null,5,now(),now()
        );
    ELSE
        INSERT INTO public.payments(
            order_id,user_id,stripe_payment_intent_id,amount,amount_paise,currency,status,
            payment_method,attempt_number,total_attempts,latest_attempt_number,successful_attempt_number,
            latest_payment_intent_id,max_attempts,created_at,updated_at
        ) VALUES (
            v_order_id,v_customer_id,v_payment_intent_id,v_total_amount,v_amount_paise,v_currency,
            'requires_payment_method',v_payment_method,null,0,null,null,v_payment_intent_id,5,now(),now()
        );
    END IF;

    FOR v_item IN SELECT * FROM jsonb_array_elements(p_items)
    LOOP
        v_merged_item := v_item || jsonb_build_object(
            'id',gen_random_uuid(),
            'order_id',v_order_id,
            'created_at',now()::text
        );
        INSERT INTO public.order_items
        SELECT * FROM jsonb_populate_record(null::public.order_items,v_merged_item);
    END LOOP;

    -- Critical coupon invariant: reserve the single-use/global-use capacity
    -- before this transaction can return an order. If reservation fails,
    -- the entire order transaction rolls back.
    v_coupon_id := nullif(trim(p_order_data->>'coupon_id'),'')::uuid;
    v_coupon_discount := COALESCE((p_order_data->>'discount_amount')::numeric,0);
    IF v_coupon_id IS NOT NULL AND v_coupon_discount > 0 THEN
        SELECT public.reserve_coupon_for_order(
            v_coupon_id,
            v_customer_id,
            v_order_id,
            v_coupon_discount
        ) INTO v_coupon_reserved;

        IF COALESCE(v_coupon_reserved,false) = false THEN
            RAISE EXCEPTION 'COUPON_RESERVATION_FAILED';
        END IF;
    END IF;

    DELETE FROM public.cart_items
     WHERE cart_id IN (SELECT id FROM public.carts WHERE user_id=v_customer_id);
    UPDATE public.carts SET updated_at=now() WHERE user_id=v_customer_id;

    SELECT row_to_json(o)::jsonb INTO v_result
      FROM public.orders o
     WHERE o.id=v_order_id;
    RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION public.create_pending_order_with_reservation(jsonb,jsonb) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb,jsonb) TO service_role;

CREATE OR REPLACE FUNCTION public.cleanup_expired_coupon_reservations()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $$
DECLARE
    v_deleted integer;
BEGIN
    DELETE FROM public.coupon_redemptions
     WHERE status = 'reserved'
       AND expires_at IS NOT NULL
       AND expires_at <= now();
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.cleanup_expired_coupon_reservations() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cleanup_expired_coupon_reservations() TO service_role;
