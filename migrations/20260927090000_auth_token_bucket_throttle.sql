-- LUVIIO — shared authentication token-bucket throttling
-- Adds an atomic token bucket to the existing DB-backed auth throttle.
-- IP and email buckets are checked independently; both must have a token.
-- Existing failed-attempt/cooldown protection remains in place.

ALTER TABLE public.auth_throttle_state
    ADD COLUMN IF NOT EXISTS tokens numeric(12,4) NOT NULL DEFAULT 5,
    ADD COLUMN IF NOT EXISTS last_refill_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE public.auth_throttle_state
    DROP CONSTRAINT IF EXISTS auth_throttle_state_tokens_nonnegative;

ALTER TABLE public.auth_throttle_state
    ADD CONSTRAINT auth_throttle_state_tokens_nonnegative
    CHECK (tokens >= 0);

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
    v_blocked boolean := false;
    v_capacity numeric(12,4);
    v_refill_interval numeric(12,4);
    v_elapsed numeric(20,6);
    v_available numeric(12,4);
    r record;
BEGIN
    IF p_window_seconds < 1 OR p_max_attempts < 1 THEN
        RAISE EXCEPTION 'invalid auth throttle configuration';
    END IF;

    -- Preserve the existing 5 attempts / 300 seconds policy while using
    -- token-bucket semantics: capacity = max attempts, one token refills
    -- every window/max-attempts seconds (5 / 300 = 1 token / 60 seconds).
    v_capacity := p_max_attempts;
    v_refill_interval := GREATEST(
        1,
        CEIL(p_window_seconds::numeric / p_max_attempts::numeric)
    );

    -- First pass only checks both buckets while holding row locks.
    -- No token is consumed unless every applicable bucket has capacity.
    FOREACH v_kind IN ARRAY ARRAY['ip','email'] LOOP
        v_key := CASE WHEN v_kind = 'ip' THEN p_ip_key ELSE p_email_key END;
        IF v_key IS NULL OR v_key = '' THEN
            CONTINUE;
        END IF;

        INSERT INTO public.auth_throttle_state(
            key_hash, key_type, attempts, window_started_at,
            blocked_until, updated_at, tokens, last_refill_at
        )
        VALUES (
            v_key, v_kind, 0, v_now, NULL, v_now,
            v_capacity, v_now
        )
        ON CONFLICT (key_type, key_hash) DO NOTHING;

        SELECT *
        INTO r
        FROM public.auth_throttle_state
        WHERE key_type = v_kind
          AND key_hash = v_key
        FOR UPDATE;

        IF r.blocked_until IS NOT NULL AND r.blocked_until > v_now THEN
            v_blocked := true;
            CONTINUE;
        END IF;

        IF v_now - r.window_started_at >= make_interval(secs => p_window_seconds) THEN
            UPDATE public.auth_throttle_state
            SET attempts = 0,
                window_started_at = v_now,
                blocked_until = NULL,
                updated_at = v_now
            WHERE key_type = v_kind
              AND key_hash = v_key;

            r.attempts := 0;
            r.window_started_at := v_now;
            r.blocked_until := NULL;
        ELSIF r.attempts >= p_max_attempts THEN
            v_blocked := true;
            CONTINUE;
        END IF;

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

    -- Second pass consumes exactly one token from each applicable bucket.
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
