-- Fix reserve_coupon_for_order: ON CONFLICT cannot target the partial unique index without its predicate.
-- Keep the explicit idempotency lookup and let the unique-index race fall through
-- to the existing unique_violation handler.

CREATE OR REPLACE FUNCTION public.reserve_coupon_for_order(
  p_coupon_id uuid,
  p_user_id uuid,
  p_order_id uuid,
  p_discount numeric
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $$
DECLARE
  v_limit integer;
  v_used integer;
  v_per_user integer;
  v_user_active integer;
  v_global_active integer;
BEGIN
  IF p_coupon_id IS NULL OR p_user_id IS NULL OR p_order_id IS NULL
     OR p_discount IS NULL OR p_discount <= 0 THEN
    RETURN false;
  END IF;

  SELECT usage_limit, COALESCE(used_count, 0), COALESCE(per_user_limit, 1)
    INTO v_limit, v_used, v_per_user
  FROM public.coupons
  WHERE id = p_coupon_id
    AND is_active = true
    AND (valid_from IS NULL OR now() >= valid_from)
    AND (valid_until IS NULL OR now() <= valid_until)
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN false;
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.coupon_redemptions
    WHERE coupon_id = p_coupon_id AND user_id = p_user_id AND order_id = p_order_id
  ) THEN
    RETURN true;
  END IF;

  SELECT count(*) INTO v_user_active
  FROM public.coupon_redemptions
  WHERE coupon_id = p_coupon_id
    AND user_id = p_user_id
    AND status IN ('reserved', 'redeemed');

  IF v_user_active >= v_per_user THEN
    RETURN false;
  END IF;

  SELECT count(*) INTO v_global_active
  FROM public.coupon_redemptions
  WHERE coupon_id = p_coupon_id
    AND status IN ('reserved', 'redeemed');

  IF v_limit IS NOT NULL AND v_global_active >= v_limit THEN
    RETURN false;
  END IF;

  INSERT INTO public.coupon_redemptions(coupon_id, user_id, order_id, discount, status)
  VALUES (p_coupon_id, p_user_id, p_order_id, p_discount, 'reserved');

  RETURN true;
EXCEPTION WHEN unique_violation THEN
  RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.reserve_coupon_for_order(uuid, uuid, uuid, numeric) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_coupon_for_order(uuid, uuid, uuid, numeric) TO service_role;
