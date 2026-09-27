-- LUVIIO — shared HTTP token-bucket rate limiting.
-- Replaces the old fixed-window HTTP counter as the single global API
-- enforcement mechanism. Endpoint-specific SlowAPI limits are removed.

create schema if not exists private;

create table if not exists private.http_token_bucket_state (
    rate_key text primary key,
    tokens numeric(14,6) not null,
    last_refill_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint http_token_bucket_tokens_nonnegative check (tokens >= 0)
);

revoke all on table private.http_token_bucket_state from public, anon, authenticated;
grant select, insert, update, delete on table private.http_token_bucket_state to service_role;

create or replace function private.consume_http_token_bucket(
    p_rate_key text,
    p_capacity integer,
    p_refill_seconds integer default 60
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_last_refill timestamptz;
    v_tokens numeric(14,6);
    v_available numeric(14,6);
    v_elapsed numeric(20,6);
    v_refill_rate numeric(20,12);
begin
    if p_rate_key is null or length(p_rate_key) = 0 then
        raise exception 'rate key is required';
    end if;
    if p_capacity < 1 or p_refill_seconds < 1 then
        raise exception 'invalid token bucket configuration';
    end if;

    insert into private.http_token_bucket_state(
        rate_key, tokens, last_refill_at, updated_at
    )
    values (p_rate_key, p_capacity, v_now, v_now)
    on conflict (rate_key) do nothing;

    select tokens, last_refill_at
    into v_tokens, v_last_refill
    from private.http_token_bucket_state
    where rate_key = p_rate_key
    for update;

    v_now := clock_timestamp();
    v_elapsed := greatest(
        0,
        extract(epoch from (v_now - v_last_refill))
    );
    v_refill_rate := p_capacity::numeric / p_refill_seconds::numeric;
    v_available := least(
        p_capacity::numeric,
        v_tokens + (v_elapsed * v_refill_rate)
    );

    if v_available < 1 then
        update private.http_token_bucket_state
        set tokens = v_available,
            last_refill_at = v_now,
            updated_at = v_now
        where rate_key = p_rate_key;

        return jsonb_build_object(
            'allowed', false,
            'tokens', v_available,
            'capacity', p_capacity,
            'retry_after_seconds',
                greatest(
                    1,
                    ceil((1 - v_available) / v_refill_rate)::integer
                )
        );
    end if;

    update private.http_token_bucket_state
    set tokens = v_available - 1,
        last_refill_at = v_now,
        updated_at = v_now
    where rate_key = p_rate_key;

    return jsonb_build_object(
        'allowed', true,
        'tokens', v_available - 1,
        'capacity', p_capacity,
        'retry_after_seconds', 0
    );
end;
$$;

revoke all on function private.consume_http_token_bucket(text, integer, integer)
from public, anon, authenticated;
grant execute on function private.consume_http_token_bucket(text, integer, integer)
to service_role;

create index if not exists idx_http_token_bucket_updated_at
    on private.http_token_bucket_state (updated_at);

create or replace function private.cleanup_http_token_bucket_state()
returns integer
language plpgsql
security definer
set search_path = pg_catalog, private
as $$
declare
    v_deleted integer;
begin
    delete from private.http_token_bucket_state
    where updated_at < clock_timestamp() - interval '24 hours';
    get diagnostics v_deleted = row_count;
    return v_deleted;
end;
$$;

revoke all on function private.cleanup_http_token_bucket_state()
from public, anon, authenticated;
grant execute on function private.cleanup_http_token_bucket_state()
to service_role;

-- Retire the old global fixed-window enforcement function. The historical
-- table/migration is intentionally retained for migration history.
drop function if exists private.consume_http_rate_limit(text, integer, integer);
