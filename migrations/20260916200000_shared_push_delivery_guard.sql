create schema if not exists private;

create table if not exists private.push_delivery_state (
    endpoint_key text primary key,
    window_started_at timestamptz not null default now(),
    window_count integer not null default 0 check (window_count >= 0),
    consecutive_failures integer not null default 0 check (consecutive_failures >= 0),
    tripped_until timestamptz null,
    updated_at timestamptz not null default now()
);

revoke all on table private.push_delivery_state from anon, authenticated, public;

create or replace function private.push_delivery_guard(p_endpoint_key text, p_limit integer default 3, p_window_seconds integer default 1, p_failure_threshold integer default 5, p_reset_seconds integer default 60)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_state private.push_delivery_state%rowtype;
begin
    if p_endpoint_key is null or length(p_endpoint_key) = 0 then
        return false;
    end if;

    insert into private.push_delivery_state(endpoint_key, window_started_at, window_count, consecutive_failures, tripped_until, updated_at)
    values (p_endpoint_key, v_now, 0, 0, null, v_now)
    on conflict (endpoint_key) do nothing;

    select * into v_state
    from private.push_delivery_state
    where endpoint_key = p_endpoint_key
    for update;

    if v_state.tripped_until is not null and v_state.tripped_until > v_now then
        update private.push_delivery_state set updated_at = v_now where endpoint_key = p_endpoint_key;
        return false;
    end if;

    if v_state.tripped_until is not null and v_state.tripped_until <= v_now then
        v_state.consecutive_failures := 0;
        v_state.tripped_until := null;
    end if;

    if v_now - v_state.window_started_at >= make_interval(secs => greatest(p_window_seconds, 1)) then
        v_state.window_started_at := v_now;
        v_state.window_count := 0;
    end if;

    if v_state.window_count >= greatest(p_limit, 1) then
        update private.push_delivery_state
        set window_started_at = v_state.window_started_at, window_count = v_state.window_count,
            consecutive_failures = v_state.consecutive_failures, tripped_until = v_state.tripped_until,
            updated_at = v_now
        where endpoint_key = p_endpoint_key;
        return false;
    end if;

    update private.push_delivery_state
    set window_started_at = v_state.window_started_at,
        window_count = v_state.window_count + 1,
        consecutive_failures = v_state.consecutive_failures,
        tripped_until = v_state.tripped_until,
        updated_at = v_now
    where endpoint_key = p_endpoint_key;
    return true;
end;
$$;

create or replace function private.push_delivery_record_success(p_endpoint_key text)
returns void
language sql
security definer
set search_path = pg_catalog, private
as $$
    update private.push_delivery_state
    set consecutive_failures = 0, tripped_until = null, updated_at = clock_timestamp()
    where endpoint_key = p_endpoint_key;
$$;

create or replace function private.push_delivery_record_failure(p_endpoint_key text, p_failure_threshold integer default 5, p_reset_seconds integer default 60)
returns void
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
begin
    if p_endpoint_key is null or length(p_endpoint_key) = 0 then
        return;
    end if;
    insert into private.push_delivery_state(endpoint_key, updated_at)
    values (p_endpoint_key, clock_timestamp())
    on conflict (endpoint_key) do nothing;
    update private.push_delivery_state
    set consecutive_failures = consecutive_failures + 1,
        tripped_until = case when consecutive_failures + 1 >= greatest(p_failure_threshold, 1)
                             then clock_timestamp() + make_interval(secs => greatest(p_reset_seconds, 1))
                             else tripped_until end,
        updated_at = clock_timestamp()
    where endpoint_key = p_endpoint_key;
end;
$$;

revoke all on function private.push_delivery_guard(text, integer, integer, integer, integer) from public, anon, authenticated;
revoke all on function private.push_delivery_record_success(text) from public, anon, authenticated;
revoke all on function private.push_delivery_record_failure(text, integer, integer) from public, anon, authenticated;
grant execute on function private.push_delivery_guard(text, integer, integer, integer, integer) to service_role;
grant execute on function private.push_delivery_record_success(text) to service_role;
grant execute on function private.push_delivery_record_failure(text, integer, integer) to service_role;

create index if not exists push_delivery_state_tripped_until_idx on private.push_delivery_state (tripped_until) where tripped_until is not null;
