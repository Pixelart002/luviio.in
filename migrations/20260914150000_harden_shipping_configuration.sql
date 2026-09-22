-- Luviio shipping hardening
-- 1) Ensure there is exactly one active shipping method at migration time.
-- 2) Prevent two active methods with a partial unique index.
-- 3) Make method switching atomic and race-safe.

DO $$
DECLARE
    v_method_id UUID;
BEGIN
    SELECT id
      INTO v_method_id
      FROM public.shipping_methods
     WHERE is_active = TRUE
     ORDER BY sort_order, created_at, id
     LIMIT 1;

    IF v_method_id IS NULL THEN
        SELECT id
          INTO v_method_id
          FROM public.shipping_methods
         ORDER BY sort_order, created_at, id
         LIMIT 1;
    END IF;

    IF v_method_id IS NULL THEN
        INSERT INTO public.shipping_methods (
            name, type, base_rate, threshold, estimated_days, is_active, sort_order
        ) VALUES (
            'Standard Shipping', 'free_threshold', 45.90, 1499.00, 3, TRUE, 0
        )
        RETURNING id INTO v_method_id;
    ELSE
        UPDATE public.shipping_methods
           SET is_active = FALSE,
               updated_at = now()
         WHERE is_active = TRUE
           AND id <> v_method_id;

        UPDATE public.shipping_methods
           SET is_active = TRUE,
               updated_at = now()
         WHERE id = v_method_id;
    END IF;
END;
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_shipping_methods_single_active
    ON public.shipping_methods (is_active)
    WHERE is_active = TRUE;

CREATE OR REPLACE FUNCTION public.activate_shipping_method(p_method_id UUID)
RETURNS SETOF public.shipping_methods
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Serialize all active-method switches across concurrent requests.
    PERFORM pg_advisory_xact_lock(hashtextextended('luviio.shipping.active_method', 0));

    IF NOT EXISTS (
        SELECT 1 FROM public.shipping_methods WHERE id = p_method_id
    ) THEN
        RAISE EXCEPTION 'Shipping method not found';
    END IF;

    UPDATE public.shipping_methods
       SET is_active = FALSE,
           updated_at = now()
     WHERE is_active = TRUE
       AND id <> p_method_id;

    UPDATE public.shipping_methods
       SET is_active = TRUE,
           updated_at = now()
     WHERE id = p_method_id;

    RETURN QUERY
    SELECT *
      FROM public.shipping_methods
     WHERE id = p_method_id;
END;
$$;

REVOKE ALL ON FUNCTION public.activate_shipping_method(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.activate_shipping_method(UUID) TO service_role;
