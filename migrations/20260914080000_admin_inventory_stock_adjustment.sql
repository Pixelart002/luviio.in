CREATE OR REPLACE FUNCTION public.admin_adjust_stock(
  p_product_id uuid,
  p_delta integer,
  p_reason text
)
RETURNS TABLE(product_id uuid, previous_stock integer, new_stock integer, delta integer, reason text)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_previous integer; v_new integer; v_sku text; v_reason text;
BEGIN
  IF p_delta = 0 THEN RAISE EXCEPTION 'STOCK_ADJUSTMENT_ZERO'; END IF;
  v_reason := NULLIF(BTRIM(p_reason), '');
  IF v_reason IS NULL THEN RAISE EXCEPTION 'STOCK_ADJUSTMENT_REASON_REQUIRED'; END IF;
  IF char_length(v_reason) > 500 THEN RAISE EXCEPTION 'STOCK_ADJUSTMENT_REASON_TOO_LONG'; END IF;
  SELECT stock, sku INTO v_previous, v_sku FROM public.products WHERE id=p_product_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'PRODUCT_NOT_FOUND'; END IF;
  IF v_previous + p_delta < 0 THEN RAISE EXCEPTION 'INSUFFICIENT_STOCK'; END IF;
  v_new := v_previous + p_delta;
  UPDATE public.products SET stock=v_new, updated_at=NOW() WHERE id=p_product_id;
  INSERT INTO public.stock_audit(product_id, sku, delta, stock_after, reason, created_at)
  VALUES(p_product_id, v_sku, p_delta, v_new, v_reason, NOW());
  RETURN QUERY SELECT p_product_id, v_previous, v_new, p_delta, v_reason;
END;
$function$;
REVOKE ALL ON FUNCTION public.admin_adjust_stock(uuid,integer,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_adjust_stock(uuid,integer,text) TO service_role;
