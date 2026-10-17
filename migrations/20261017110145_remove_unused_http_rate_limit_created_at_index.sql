-- The rate-limit state is only read/upserted by consume_http_rate_limit()
-- on (rate_key, window_start). Cleanup filters by window_start. There is no
-- query path that filters by created_at, so this secondary index adds write
-- overhead to a hot table without supporting the observed workload.
DROP INDEX IF EXISTS private.idx_http_rate_limit_state_created_at;
