-- LUVIIO — make authentication throttling token-bucket only
-- Removes the legacy fixed-window/cooldown state so auth has one
-- enforcement algorithm: the shared Postgres token bucket.

DROP FUNCTION IF EXISTS public.auth_throttle_record_failure(text,text,integer,integer,integer);
DROP FUNCTION IF EXISTS public.auth_throttle_reset(text,text);

ALTER TABLE public.auth_throttle_state
    DROP COLUMN IF EXISTS attempts,
    DROP COLUMN IF EXISTS window_started_at,
    DROP COLUMN IF EXISTS blocked_until;

CREATE OR REPLACE FUNCTION public.auth_throttle_check(
    p_ip_key text,
    p_email_key text,
    p_window_seconds integer,
    p_max_attempts integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_key text;
    v_kind text;
    v_capacity numeric(12,4);
    v_refill_interval numeric(12,4);
    v_elapsed numeric(20,6);
    v_available numeric(12,4);
    v_blocked boolean := false;
    r record;
BEGIN
    IF p_window_seconds < 1 OR p_max_attempts < 1 THEN
        RAISE EXCEPTION 'invalid auth throttle configuration';
    END IF;

    v_capacity := p_max_attempts;
    v_refill_interval := GREATEST(
        1,
        CEIL(p_window_seconds::numeric / p_max_attempts::numeric)
    );

    -- Lock every applicable bucket before making the decision. If either
    -- bucket is empty, nothing is consumed from either bucket.
    FOREACH v_kind IN ARRAY ARRAY['ip','email'] LOOP
        v_key := CASE WHEN v_kind = 'ip' THEN p_ip_key ELSE p_email_key END;
        IF v_key IS NULL OR v_key = '' THEN
            CONTINUE;
        END IF;

        INSERT INTO public.auth_throttle_state(
            key_hash, key_type, updated_at, tokens, last_refill_at
        )
        VALUES (
            v_key, v_kind, v_now, v_capacity, v_now
        )
        ON CONFLICT (key_type, key_hash) DO NOTHING;

        SELECT *
        INTO r
        FROM public.auth_throttle_state
        WHERE key_type = v_kind
          AND key_hash = v_key
        FOR UPDATE;

        v_elapsed := GREATEST(
            0,
            EXTRACT(EPOCH FROM (v_now - COALESCE(r.last_refill_at, v_now)))
        );

        v_available := LEAST(
            v_capacity,
            COALESCE(r.tokens, v_capacity)
                + (v_elapsed / v_refill_interval)
        );

        IF v_available < 1 THEN
            v_blocked := true;
        END IF;
    END LOOP;

    IF v_blocked THEN
        RETURN false;
    END IF;

    -- Consume exactly one token from every applicable bucket atomically.
    FOREACH v_kind IN ARRAY ARRAY['ip','email'] LOOP
        v_key := CASE WHEN v_kind = 'ip' THEN p_ip_key ELSE p_email_key END;
        IF v_key IS NULL OR v_key = '' THEN
            CONTINUE;
        END IF;

        SELECT *
        INTO r
        FROM public.auth_throttle_state
        WHERE key_type = v_kind
          AND key_hash = v_key
        FOR UPDATE;

        v_elapsed := GREATEST(
            0,
            EXTRACT(EPOCH FROM (v_now - COALESCE(r.last_refill_at, v_now)))
        );

        v_available := LEAST(
            v_capacity,
            COALESCE(r.tokens, v_capacity)
                + (v_elapsed / v_refill_interval)
        );

        UPDATE public.auth_throttle_state
        SET tokens = GREATEST(0, v_available - 1),
            last_refill_at = v_now,
            updated_at = v_now
        WHERE key_type = v_kind
          AND key_hash = v_key;
    END LOOP;

    RETURN true;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.auth_throttle_check(text,text,integer,integer)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.auth_throttle_check(text,text,integer,integer)
TO service_role;
