-- Schedule low-cost housekeeping in Supabase Cron.
-- Jobs are named and cron.schedule upserts the schedule by job name.
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;

GRANT USAGE ON SCHEMA cron TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA cron TO postgres;

SELECT cron.schedule(
  'luviio-rate-limit-cleanup',
  '*/15 * * * *',
  'SELECT private.cleanup_http_rate_limit_state();'
);

SELECT cron.schedule(
  'luviio-token-bucket-cleanup',
  '17 * * * *',
  'SELECT private.cleanup_http_token_bucket_state();'
);

SELECT cron.schedule(
  'luviio-expired-coupon-reservations-cleanup',
  '*/15 * * * *',
  'SELECT public.cleanup_expired_coupon_reservations();'
);

-- Supabase Cron does not remove historical run records automatically.
SELECT cron.schedule(
  'luviio-cron-history-cleanup',
  '30 3 * * *',
  $$DELETE FROM cron.job_run_details WHERE end_time < now() - interval '7 days';$$
);
