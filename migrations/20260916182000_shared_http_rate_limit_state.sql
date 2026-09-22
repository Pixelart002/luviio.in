-- Shared cross-worker HTTP rate-limit state.
-- SlowAPI remains available for endpoint-specific limits, while this
-- Postgres-backed gate enforces the global per-IP ceiling across workers.

create schema if not exists private;

create table if not exists private.http_rate_limit_state (
    rate_key text not null,
    window_start timestamptz not null,
    request_count integer not null default 0,
    created_at timestamptz not null default now(),
    primary key (rate_key, window_start),
    constraint http_rate_limit_state_count_positive check (request_count >= 0)
);

revoke all on table private.http_rate_limit_state from public, anon, authenticated;
grant select, insert, update, delete on table private.http_rate_limit_state to service_role;

create or replace function private.consume_http_rate_limit(
    p_rate_key text,
    p_limit integer,
    p_window_seconds integer default 60
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_window_start timestamptz;
    v_count integer;
begin
    if p_rate_key is null or length(p_rate_key) = 0 then
        raise exception 'rate key is required';
    end if;
    if p_limit < 1 or p_window_seconds < 1 then
        raise exception 'invalid rate limit configuration';
    end if;

    v_window_start := to_timestamp(
        floor(extract(epoch from v_now) / p_window_seconds) * p_window_seconds
    );

    insert into private.http_rate_limit_state(rate_key, window_start, request_count)
    values (p_rate_key, v_window_start, 1)
    on conflict (rate_key, window_start)
    do update set request_count = private.http_rate_limit_state.request_count + 1
    returning request_count into v_count;

    return jsonb_build_object(
        'allowed', v_count <= p_limit,
        'count', v_count,
        'limit', p_limit,
        'window_start', v_window_start,
        'retry_after_seconds', case
            when v_count <= p_limit then 0
            else greatest(1, p_window_seconds - floor(extract(epoch from (v_now - v_window_start)))::integer)
        end
    );
end;
$$;

revoke all on function private.consume_http_rate_limit(text, integer, integer) from public, anon, authenticated;
grant execute on function private.consume_http_rate_limit(text, integer, integer) to service_role;

create index if not exists idx_http_rate_limit_state_created_at
    on private.http_rate_limit_state (created_at);

create or replace function private.cleanup_http_rate_limit_state()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
declare
    v_deleted integer;
begin
    delete from private.http_rate_limit_state
    where window_start < clock_timestamp() - interval '2 hours';
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function private.cleanup_http_rate_limit_state() from public, anon, authenticated;
grant execute on function private.cleanup_http_rate_limit_state() to service_role;
