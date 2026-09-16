-- Restore the PostgREST-visible RPC expected by the API while keeping
-- the actual rate-limit state/function private and service-role-only.

create or replace function public.consume_http_rate_limit(
    p_rate_key text,
    p_limit integer,
    p_window_seconds integer default 60
)
returns jsonb
language sql
security definer
set search_path = pg_catalog, private
as $$
    select private.consume_http_rate_limit(p_rate_key, p_limit, p_window_seconds);
$$;

revoke all on function public.consume_http_rate_limit(text, integer, integer) from public, anon, authenticated;
grant execute on function public.consume_http_rate_limit(text, integer, integer) to service_role;

notify pgrst, 'reload schema';
