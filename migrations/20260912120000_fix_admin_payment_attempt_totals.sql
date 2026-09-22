CREATE OR REPLACE FUNCTION public.admin_payment_telemetry(p_limit integer DEFAULT 10, p_offset integer DEFAULT 0)
RETURNS TABLE (
  id uuid, order_id uuid, amount numeric, amount_paise bigint, currency text,
  status text, payment_method text, error_code text, error_message text,
  attempt_number integer, total_attempts integer, latest_payment_intent_id text,
  created_at timestamptz, updated_at timestamptz, order_number text,
  order_status text, total_amount numeric, total_count bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  WITH events AS (
    SELECT
      p.id,
      p.order_id,
      p.amount,
      p.amount_paise,
      p.currency,
      p.status,
      COALESCE(p.payment_method, o.payment_method) AS payment_method,
      p.error_code,
      p.error_message,
      p.attempt_number,
      COUNT(*) OVER (PARTITION BY p.order_id)::integer AS total_attempts,
      p.latest_payment_intent_id,
      p.created_at,
      p.updated_at,
      o.order_number,
      o.status AS order_status,
      o.total_amount
    FROM public.payments p
    LEFT JOIN public.orders o ON o.id = p.order_id

    UNION ALL

    SELECT
      o.id,
      o.id,
      o.total_amount,
      ROUND(o.total_amount * 100)::bigint,
      COALESCE(o.currency, 'INR'),
      o.status,
      'cod',
      NULL,
      NULL,
      1,
      1,
      NULL,
      o.created_at,
      o.updated_at,
      o.order_number,
      o.status,
      o.total_amount
    FROM public.orders o
    WHERE o.payment_method = 'cod'
      AND NOT EXISTS (SELECT 1 FROM public.payments p WHERE p.order_id = o.id)
  )
  SELECT e.*, COUNT(*) OVER() AS total_count
  FROM events e
  ORDER BY e.created_at DESC, e.id DESC
  LIMIT LEAST(GREATEST(p_limit, 1), 50)
  OFFSET GREATEST(p_offset, 0);
$$;

REVOKE ALL ON FUNCTION public.admin_payment_telemetry(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_payment_telemetry(integer, integer) TO service_role;
