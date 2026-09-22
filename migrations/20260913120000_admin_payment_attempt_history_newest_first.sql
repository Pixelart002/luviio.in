-- Show durable payment attempts as individual admin payment events, newest first.
-- This prevents failed attempts from disappearing behind the single canonical payments row.
CREATE OR REPLACE FUNCTION public.admin_payment_telemetry(p_limit integer DEFAULT 10, p_offset integer DEFAULT 0)
RETURNS TABLE(
  id uuid,
  order_id uuid,
  amount numeric,
  amount_paise bigint,
  currency text,
  status text,
  payment_method text,
  error_code text,
  error_message text,
  attempt_number integer,
  total_attempts integer,
  latest_payment_intent_id text,
  created_at timestamptz,
  updated_at timestamptz,
  order_number text,
  order_status text,
  total_amount numeric,
  total_count bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_catalog
AS $$
  WITH attempt_rows AS (
    SELECT
      pa.id,
      pa.order_id,
      COALESCE(pa.amount, p.amount, o.total_amount) AS amount,
      COALESCE(pa.amount_paise, p.amount_paise, ROUND(o.total_amount * 100)::bigint) AS amount_paise,
      COALESCE(pa.currency, p.currency, o.currency, 'INR') AS currency,
      CASE
        WHEN pa.status IN ('requires_payment_method','failed','canceled','cancelled') THEN 'failed'
        ELSE pa.status
      END AS status,
      COALESCE(p.payment_method, o.payment_method, 'card') AS payment_method,
      p.error_code,
      pa.error_message,
      pa.attempt_number,
      GREATEST(
        COALESCE(p.total_attempts, 0),
        COALESCE((SELECT MAX(x.attempt_number) FROM public.payment_attempts x WHERE x.order_id = pa.order_id), 0),
        pa.attempt_number
      )::integer AS total_attempts,
      COALESCE(p.latest_payment_intent_id, pa.stripe_payment_intent_id) AS latest_payment_intent_id,
      pa.created_at,
      COALESCE(p.updated_at, pa.created_at) AS updated_at,
      o.order_number,
      o.status AS order_status,
      o.total_amount
    FROM public.payment_attempts AS pa
    LEFT JOIN public.payments AS p ON p.id = pa.payment_id
    LEFT JOIN public.orders AS o ON o.id = pa.order_id
  ),
  payment_without_attempt AS (
    SELECT
      p.id,
      p.order_id,
      p.amount,
      p.amount_paise::bigint,
      p.currency,
      CASE WHEN p.status IN ('requires_payment_method','failed','canceled','cancelled') THEN 'failed' ELSE p.status END AS status,
      COALESCE(p.payment_method, o.payment_method, 'card') AS payment_method,
      p.error_code,
      p.error_message,
      GREATEST(COALESCE(p.attempt_number, 1), 1)::integer AS attempt_number,
      GREATEST(COALESCE(p.total_attempts, 1), COALESCE(p.attempt_number, 1), 1)::integer AS total_attempts,
      p.latest_payment_intent_id,
      p.created_at,
      p.updated_at,
      o.order_number,
      o.status AS order_status,
      o.total_amount
    FROM public.payments AS p
    LEFT JOIN public.orders AS o ON o.id = p.order_id
    WHERE NOT EXISTS (SELECT 1 FROM public.payment_attempts AS pa WHERE pa.order_id = p.order_id)
  ),
  cod_rows AS (
    SELECT
      o.id,
      o.id AS order_id,
      o.total_amount,
      ROUND(o.total_amount * 100)::bigint,
      COALESCE(o.currency, 'INR'),
      'succeeded'::text,
      'cod'::text,
      NULL::text,
      NULL::text,
      1::integer,
      1::integer,
      NULL::text,
      o.created_at,
      o.updated_at,
      o.order_number,
      o.status,
      o.total_amount
    FROM public.orders AS o
    WHERE o.payment_method = 'cod'
      AND NOT EXISTS (SELECT 1 FROM public.payments AS p WHERE p.order_id = o.id)
      AND NOT EXISTS (SELECT 1 FROM public.payment_attempts AS pa WHERE pa.order_id = o.id)
  ),
  events AS (
    SELECT * FROM attempt_rows
    UNION ALL
    SELECT * FROM payment_without_attempt
    UNION ALL
    SELECT * FROM cod_rows
  )
  SELECT e.*, COUNT(*) OVER() AS total_count
  FROM events AS e
  ORDER BY e.created_at DESC, e.id DESC
  LIMIT LEAST(GREATEST(p_limit, 1), 50)
  OFFSET GREATEST(p_offset, 0);
$$;

REVOKE ALL ON FUNCTION public.admin_payment_telemetry(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_payment_telemetry(integer, integer) TO service_role;
