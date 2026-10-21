-- Consolidated admin dashboard payload: one PostgREST RPC instead of many
-- client requests and an unbounded, page-by-page inventory scan.
-- All totals are computed in PostgreSQL; chart buckets are based on real order dates.

CREATE INDEX IF NOT EXISTS idx_orders_dashboard_created_at
  ON public.orders (created_at DESC)
  INCLUDE (status, total_amount, order_number, payment_method);

CREATE INDEX IF NOT EXISTS idx_products_dashboard_active_stock
  ON public.products (is_active, stock)
  INCLUDE (low_stock_threshold);

CREATE INDEX IF NOT EXISTS idx_audit_logs_dashboard_created_at
  ON public.audit_logs (created_at DESC)
  INCLUDE (status_code);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_dashboard_user
  ON public.push_subscriptions (user_id);

CREATE OR REPLACE FUNCTION public.admin_dashboard_snapshot(p_days integer DEFAULT 30)
RETURNS jsonb
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
WITH params AS (
  SELECT LEAST(GREATEST(COALESCE(p_days, 30), 7), 90)::integer AS days
),
order_metrics AS (
  SELECT
    COUNT(*)::bigint AS orders,
    COUNT(*) FILTER (WHERE status = 'pending')::bigint AS pending_orders,
    COALESCE(
      SUM(total_amount) FILTER (
        WHERE status IN ('paid', 'processing', 'shipped', 'delivered')
      ),
      0
    )::numeric AS revenue
  FROM public.orders
),
product_metrics AS (
  SELECT
    COUNT(*) FILTER (WHERE is_active = true)::bigint AS products_scanned,
    COALESCE(SUM(stock) FILTER (WHERE is_active = true), 0)::bigint AS units,
    COUNT(*) FILTER (WHERE is_active = true AND COALESCE(stock, 0) <= 0)::bigint AS out_of_stock,
    COUNT(*) FILTER (
      WHERE is_active = true
        AND COALESCE(stock, 0) <= COALESCE(low_stock_threshold, 10)
    )::bigint AS low_stock
  FROM public.products
),
user_metrics AS (
  SELECT COUNT(*)::bigint AS users FROM public.users
),
recent_orders AS (
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'id', recent.id,
        'order_number', recent.order_number,
        'status', recent.status,
        'total_amount', recent.total_amount,
        'created_at', recent.created_at
      ) ORDER BY recent.created_at DESC
    ),
    '[]'::jsonb
  ) AS items
  FROM (
    SELECT id, order_number, status, total_amount, created_at
    FROM public.orders
    ORDER BY created_at DESC
    LIMIT 5
  ) AS recent
),
calendar AS (
  SELECT generate_series(
    CURRENT_DATE - ((SELECT days FROM params) - 1),
    CURRENT_DATE,
    INTERVAL '1 day'
  )::date AS day
),
daily_orders AS (
  SELECT
    created_at::date AS day,
    COUNT(*)::bigint AS orders,
    COALESCE(
      SUM(total_amount) FILTER (
        WHERE status IN ('paid', 'processing', 'shipped', 'delivered')
      ),
      0
    )::numeric AS revenue
  FROM public.orders
  WHERE created_at >= CURRENT_DATE - ((SELECT days FROM params) - 1)
    AND created_at < CURRENT_DATE + INTERVAL '1 day'
  GROUP BY created_at::date
),
revenue_series AS (
  SELECT COALESCE(
    jsonb_agg(
      jsonb_build_object(
        'date', to_char(calendar.day, 'YYYY-MM-DD'),
        'orders', COALESCE(daily_orders.orders, 0),
        'revenue', COALESCE(daily_orders.revenue, 0)
      ) ORDER BY calendar.day
    ),
    '[]'::jsonb
  ) AS points
  FROM calendar
  LEFT JOIN daily_orders USING (day)
),
payment_events AS (
  SELECT status, payment_method, order_status, amount
  FROM public.admin_payment_telemetry(50, 0)
),
payment_summary AS (
  SELECT
    COUNT(*)::bigint AS attempts,
    COALESCE(SUM(amount), 0)::numeric AS event_value,
    COUNT(*) FILTER (
      WHERE (
        lower(COALESCE(payment_method, '')) = 'cod'
        AND lower(COALESCE(order_status, '')) IN ('paid', 'processing', 'shipped', 'delivered')
      )
      OR lower(COALESCE(status, '')) IN ('succeeded', 'paid')
    )::bigint AS succeeded,
    COUNT(*) FILTER (
      WHERE lower(COALESCE(status, '')) IN ('failed', 'canceled', 'cancelled')
    )::bigint AS failed
  FROM payment_events
),
recent_audit AS (
  SELECT status_code
  FROM public.audit_logs
  ORDER BY created_at DESC
  LIMIT 200
),
audit_summary AS (
  SELECT
    COUNT(*)::bigint AS entries,
    COUNT(*) FILTER (WHERE status_code >= 200 AND status_code < 400)::bigint AS successful,
    COUNT(*) FILTER (WHERE status_code >= 400)::bigint AS errors
  FROM recent_audit
),
push_summary AS (
  SELECT
    COUNT(*)::bigint AS total_subscriptions,
    COUNT(DISTINCT user_id)::bigint AS unique_users
  FROM public.push_subscriptions
),
stripe_setting AS (
  SELECT COALESCE((
    SELECT value #>> '{}'
    FROM public.system_settings
    WHERE key = 'stripe_publishable_key'
    LIMIT 1
  ), '') AS publishable_key
)
SELECT jsonb_build_object(
  'stats', jsonb_build_object(
    'products', product_metrics.products_scanned,
    'orders', order_metrics.orders,
    'pending_orders', order_metrics.pending_orders,
    'users', user_metrics.users,
    'revenue', order_metrics.revenue
  ),
  'recent_orders', recent_orders.items,
  'inventory', jsonb_build_object(
    'units', product_metrics.units,
    'outOfStock', product_metrics.out_of_stock,
    'productsScanned', product_metrics.products_scanned,
    'truncated', false
  ),
  'low_stock', product_metrics.low_stock,
  'payments', jsonb_build_object(
    'attempts', payment_summary.attempts,
    'eventValue', payment_summary.event_value,
    'succeeded', payment_summary.succeeded,
    'failed', payment_summary.failed
  ),
  'audit', jsonb_build_object(
    'entries', audit_summary.entries,
    'successful', audit_summary.successful,
    'errors', audit_summary.errors
  ),
  'notifications', jsonb_build_object(
    'total_subscriptions', push_summary.total_subscriptions,
    'unique_users', push_summary.unique_users,
    'avg_per_user', CASE
      WHEN push_summary.unique_users > 0
        THEN round(push_summary.total_subscriptions::numeric / push_summary.unique_users, 1)
      ELSE 0
    END,
    'vapid_configured', false
  ),
  'stripe', jsonb_build_object(
    'status', CASE
      WHEN COALESCE(stripe_setting.publishable_key, '') ~ '^pk_(test|live)_[A-Za-z0-9]+$'
        THEN 'Configured'
      ELSE 'Missing'
    END,
    'mode', CASE
      WHEN COALESCE(stripe_setting.publishable_key, '') LIKE 'pk_live_%' THEN 'Live'
      WHEN COALESCE(stripe_setting.publishable_key, '') LIKE 'pk_test_%' THEN 'Test'
      ELSE 'Not configured'
    END,
    'storage', 'Runtime settings'
  ),
  'revenue_series', revenue_series.points,
  'date_range', jsonb_build_object(
    'days', (SELECT days FROM params),
    'from', to_char(CURRENT_DATE - ((SELECT days FROM params) - 1), 'YYYY-MM-DD'),
    'to', to_char(CURRENT_DATE, 'YYYY-MM-DD')
  ),
  'generated_at', now()
)
FROM order_metrics
CROSS JOIN product_metrics
CROSS JOIN user_metrics
CROSS JOIN recent_orders
CROSS JOIN revenue_series
CROSS JOIN payment_summary
CROSS JOIN audit_summary
CROSS JOIN push_summary
CROSS JOIN stripe_setting;
$function$;

REVOKE ALL ON FUNCTION public.admin_dashboard_snapshot(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.admin_dashboard_snapshot(integer) TO service_role;
