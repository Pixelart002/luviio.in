-- The two-argument cancellation function was introduced by older checkout
-- migrations and still restores cancelled order items to the cart. Some active
-- callers (checkout cancellation and abandoned-order cleanup) still resolve to
-- this overload, so redefining only the three-argument function is insufficient.
-- Keep the legacy signature for compatibility but delegate to the authoritative
-- three-argument function, which never recreates cart/cart_items.

CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(
    p_order_id uuid,
    p_reason text DEFAULT 'order_cancelled'::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public'
AS $function$
BEGIN
    RETURN public.cancel_order_and_release_stock(
        p_order_id,
        p_reason,
        'cancelled'::text
    );
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text)
    TO service_role;
