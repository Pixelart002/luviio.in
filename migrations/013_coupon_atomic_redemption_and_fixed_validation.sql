-- Coupon integrity hardening
-- Applied to the Luviio Supabase project as migration:
-- coupon_atomic_redemption_and_fixed_validation + coupon_redemption_atomic_rpc

CREATE OR REPLACE FUNCTION public.consume_coupon(p_coupon_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_updated integer;
BEGIN
  UPDATE public.coupons
     SET used_count = COALESCE(used_count, 0) + 1,
         updated_at = now()
   WHERE id = p_coupon_id
     AND is_active = true
     AND (usage_limit IS NULL OR COALESCE(used_count, 0) < usage_limit);
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated = 1;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.consume_coupon(uuid) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_coupon(uuid) TO service_role;

ALTER TABLE public.coupons DROP CONSTRAINT IF EXISTS coupons_value_check;
ALTER TABLE public.coupons ADD CONSTRAINT coupons_value_check CHECK (
  value > 0 AND ((type = 'percent' AND value <= 100) OR type = 'fixed')
);

CREATE OR REPLACE FUNCTION public.record_coupon_redemption(
  p_coupon_id uuid,
  p_user_id uuid,
  p_order_id uuid,
  p_discount numeric
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_limit integer;
  v_used integer;
  v_per_user integer;
  v_user_used integer;
BEGIN
  SELECT usage_limit, COALESCE(used_count, 0), COALESCE(per_user_limit, 1)
    INTO v_limit, v_used, v_per_user
    FROM public.coupons
   WHERE id = p_coupon_id AND is_active = true
   FOR UPDATE;

  IF NOT FOUND THEN RETURN false; END IF;
  IF v_limit IS NOT NULL AND v_used >= v_limit THEN RETURN false; END IF;

  SELECT count(*) INTO v_user_used
    FROM public.coupon_redemptions
   WHERE coupon_id = p_coupon_id AND user_id = p_user_id;
  IF v_user_used >= v_per_user THEN RETURN false; END IF;

  INSERT INTO public.coupon_redemptions (coupon_id, user_id, order_id, discount)
  VALUES (p_coupon_id, p_user_id, p_order_id, p_discount);

  UPDATE public.coupons
     SET used_count = v_used + 1, updated_at = now()
   WHERE id = p_coupon_id;
  RETURN true;
EXCEPTION WHEN unique_violation THEN
  RETURN false;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.record_coupon_redemption(uuid, uuid, uuid, numeric) FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_coupon_redemption(uuid, uuid, uuid, numeric) TO service_role;
