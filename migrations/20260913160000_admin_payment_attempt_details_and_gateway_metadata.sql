-- Admin payment history: expose every attempt with gateway/client telemetry.
-- This is read-only admin telemetry; payment secrets and card data are never stored here.

DROP FUNCTION IF EXISTS public.admin_payment_telemetry(integer,integer);

CREATE FUNCTION public.admin_payment_telemetry(
  p_limit integer DEFAULT 10,
  p_offset integer DEFAULT 0
)
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
  max_attempts integer,
  stripe_payment_intent_id text,
  gateway_metadata jsonb,
  ip_address text,
  user_agent text,
  created_at timestamptz,
  updated_at timestamptz,
  order_number text,
  order_status text,
  total_amount numeric,
  total_count bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
WITH durable_attempts AS (
  SELECT pa.id,pa.order_id,pa.amount,pa.amount_paise,pa.currency,pa.status,
    COALESCE(pa.payment_method,p.payment_method,o.payment_method,'card') AS payment_method,
    pa.error_code,pa.error_message,pa.attempt_number,COALESCE(p.max_attempts,5)::integer AS max_attempts,
    pa.stripe_payment_intent_id::text,COALESCE(pa.gateway_metadata,p.gateway_metadata,'{}'::jsonb) AS gateway_metadata,
    pa.ip_address,pa.user_agent,pa.created_at,pa.updated_at,o.order_number,o.status AS order_status,o.total_amount
  FROM public.payment_attempts pa
  LEFT JOIN public.payments p ON p.id=pa.payment_id AND p.order_id=pa.order_id
  LEFT JOIN public.orders o ON o.id=pa.order_id
), expired_slots AS (
  SELECT r.id,r.order_id,COALESCE(p.amount,o.total_amount,0)::numeric AS amount,
    ROUND(COALESCE(p.amount,o.total_amount,0)*100)::bigint AS amount_paise,
    COALESCE(p.currency,o.currency,'INR')::text AS currency,'expired'::text AS status,
    COALESCE(p.payment_method,o.payment_method,'card')::text AS payment_method,NULL::text AS error_code,
    'Payment retry reservation expired.'::text AS error_message,r.attempt_number,COALESCE(p.max_attempts,5)::integer AS max_attempts,
    r.stripe_payment_intent_id::text,COALESCE(p.gateway_metadata,'{}'::jsonb) AS gateway_metadata,
    NULL::text AS ip_address,NULL::text AS user_agent,r.created_at,COALESCE(r.released_at,r.expires_at,r.created_at) AS updated_at,
    o.order_number,o.status AS order_status,o.total_amount
  FROM public.payment_retry_reservations r
  LEFT JOIN public.payments p ON p.order_id=r.order_id
  LEFT JOIN public.orders o ON o.id=r.order_id
  WHERE r.status='expired' AND NOT EXISTS (
    SELECT 1 FROM public.payment_attempts pa WHERE pa.order_id=r.order_id AND pa.attempt_number=r.attempt_number
  )
), cod_rows AS (
  SELECT o.id,o.id AS order_id,o.total_amount,ROUND(o.total_amount*100)::bigint,COALESCE(o.currency,'INR')::text,
    'pending'::text,'cod'::text,NULL::text,NULL::text,1,5::integer,NULL::text,'{}'::jsonb,NULL::text,NULL::text,
    o.created_at,o.updated_at,o.order_number,o.status AS order_status,o.total_amount
  FROM public.orders o
  WHERE o.payment_method='cod'
    AND NOT EXISTS (SELECT 1 FROM public.payments p WHERE p.order_id=o.id)
    AND NOT EXISTS (SELECT 1 FROM public.payment_attempts pa WHERE pa.order_id=o.id)
), events AS (
  SELECT * FROM durable_attempts UNION ALL SELECT * FROM expired_slots UNION ALL SELECT * FROM cod_rows
)
SELECT e.id,e.order_id,e.amount,e.amount_paise,e.currency,e.status,e.payment_method,e.error_code,e.error_message,
  e.attempt_number,e.max_attempts,e.stripe_payment_intent_id,e.gateway_metadata,e.ip_address,e.user_agent,
  e.created_at,e.updated_at,e.order_number,e.order_status,e.total_amount,COUNT(*) OVER() AS total_count
FROM events e
ORDER BY e.order_number DESC,e.attempt_number ASC,e.created_at ASC,e.id ASC
LIMIT LEAST(GREATEST(p_limit,1),50) OFFSET GREATEST(p_offset,0);
$function$;

REVOKE ALL ON FUNCTION public.admin_payment_telemetry(integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_payment_telemetry(integer,integer) TO service_role;
