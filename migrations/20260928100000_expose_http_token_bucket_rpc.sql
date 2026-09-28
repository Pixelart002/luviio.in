-- LUVIIO — expose the shared HTTP token bucket through PostgREST.
-- The state and implementation remain private; only service_role can execute the public RPC wrapper.

create or replace function public.consume_http_token_bucket(
    p_rate_key text,
    p_capacity integer,
    p_refill_seconds integer default 60
)
returns jsonb
language sql
security definer
set search_path = pg_catalog, public, private
as $$
    select private.consume_http_token_bucket(
        p_rate_key,
        p_capacity,
        p_refill_seconds
    );
$$;

revoke all on function public.consume_http_token_bucket(text, integer, integer)
from public, anon, authenticated;
grant execute on function public.consume_http_token_bucket(text, integer, integer)
to service_role;
