-- Expose a service-role-only PostgREST entrypoint for scheduled cleanup.
-- pg_cron is not installed in this project; the application scheduler owns this task.

create or replace function public.cleanup_http_token_bucket_state()
returns integer
language sql
security definer
set search_path = pg_catalog, public, private
as $$
    select private.cleanup_http_token_bucket_state();
$$;

revoke all on function public.cleanup_http_token_bucket_state()
from public, anon, authenticated;

grant execute on function public.cleanup_http_token_bucket_state()
to service_role;
