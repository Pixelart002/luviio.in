-- Coupon lifecycle hardening: normalize codes, enforce invariants, and make redemption idempotent/concurrency-safe.

UPDATE public.coupons
SET code = upper(btrim(code)), updated_at = now()
WHERE code IS DISTINCT FROM upper(btrim(code));

ALTER TABLE public.coupons
  DROP CONSTRAINT IF EXISTS coupons_code_format_check,
  DROP CONSTRAINT IF EXISTS coupons_valid_window_check,
  DROP CONSTRAINT IF EXISTS coupons_numeric_integrity_check;

ALTER TABLE public.coupons
  ADD CONSTRAINT coupons_code_format_check
    CHECK (code = upper(btrim(code)) AND length(code) >= 3 AND length(code) <= 50),
  ADD CONSTRAINT coupons_valid_window_check
    CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_until > valid_from),
  ADD CONSTRAINT coupons_numeric_integrity_check
    CHECK (
      min_order_amount >= 0
      AND per_user_limit >= 1
      AND used_count >= 0
      AND (max_discount IS NULL OR max_discount > 0)
    );

CREATE UNIQUE INDEX IF NOT EXISTS coupons_code_upper_unique_idx
  ON public.coupons (upper(code));

CREATE UNIQUE INDEX IF NOT EXISTS coupon_redemptions_coupon_user_order_unique_idx
  ON public.coupon_redemptions (coupon_id, user_id, order_id)
  WHERE order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS coupon_redemptions_coupon_status_idx
  ON public.coupon_redemptions (coupon_id, status);

CREATE INDEX IF NOT EXISTS coupon_redemptions_coupon_user_status_idx
  ON public.coupon_redemptions (coupon_id, user_id, status);

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
  IF p_coupon_id IS NULL OR p_user_id IS NULL OR p_order_id IS NULL OR p_discount IS NULL OR p_discount <= 0 THEN
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
    SELECT 1
    FROM public.coupon_redemptions
    WHERE coupon_id = p_coupon_id
      AND user_id = p_user_id
      AND order_id = p_order_id
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

CREATE OR REPLACE FUNCTION public.record_coupon_redemption(
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
  v_status text;
  v_limit integer;
  v_used integer;
  v_per_user integer;
  v_user_redeemed integer;
BEGIN
  IF p_coupon_id IS NULL OR p_user_id IS NULL OR p_order_id IS NULL OR p_discount IS NULL OR p_discount <= 0 THEN
    RETURN false;
  END IF;

  SELECT status INTO v_status
  FROM public.coupon_redemptions
  WHERE coupon_id = p_coupon_id AND user_id = p_user_id AND order_id = p_order_id
  FOR UPDATE;

  IF v_status = 'redeemed' THEN
    RETURN true;
  END IF;
  IF v_status <> 'reserved' THEN
    RETURN false;
  END IF;

  SELECT usage_limit, COALESCE(used_count, 0), COALESCE(per_user_limit, 1)
    INTO v_limit, v_used, v_per_user
  FROM public.coupons
  WHERE id = p_coupon_id AND is_active = true
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN false;
  END IF;
  IF v_limit IS NOT NULL AND v_used >= v_limit THEN
    RETURN false;
  END IF;

  SELECT count(*) INTO v_user_redeemed
  FROM public.coupon_redemptions
  WHERE coupon_id = p_coupon_id AND user_id = p_user_id AND status = 'redeemed';

  IF v_user_redeemed >= v_per_user THEN
    RETURN false;
  END IF;

  UPDATE public.coupon_redemptions
  SET status = 'redeemed', discount = p_discount
  WHERE coupon_id = p_coupon_id AND user_id = p_user_id AND order_id = p_order_id AND status = 'reserved';

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
