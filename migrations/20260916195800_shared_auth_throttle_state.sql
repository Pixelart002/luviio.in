CREATE TABLE IF NOT EXISTS public.auth_throttle_state (
    key_hash text NOT NULL,
    key_type text NOT NULL CHECK (key_type IN ('ip','email')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    window_started_at timestamptz NOT NULL DEFAULT now(),
    blocked_until timestamptz NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (key_type, key_hash)
);

ALTER TABLE public.auth_throttle_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_throttle_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deny_client_all ON public.auth_throttle_state;
CREATE POLICY deny_client_all ON public.auth_throttle_state AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false);
REVOKE ALL ON public.auth_throttle_state FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.auth_throttle_state TO service_role;

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
    v_now timestamptz := now();
    v_key text;
    v_kind text;
    v_blocked boolean := false;
    r record;
BEGIN
    FOREACH v_kind IN ARRAY ARRAY['ip','email'] LOOP
        v_key := CASE WHEN v_kind = 'ip' THEN p_ip_key ELSE p_email_key END;
        IF v_key IS NULL OR v_key = '' THEN CONTINUE; END IF;

        INSERT INTO public.auth_throttle_state(key_hash,key_type,attempts,window_started_at,updated_at)
        VALUES(v_key,v_kind,0,v_now,v_now)
        ON CONFLICT (key_type,key_hash) DO NOTHING;

        SELECT * INTO r
        FROM public.auth_throttle_state
        WHERE key_type = v_kind AND key_hash = v_key
        FOR UPDATE;

        IF r.blocked_until IS NOT NULL AND r.blocked_until > v_now THEN
            v_blocked := true;
        ELSIF v_now - r.window_started_at >= make_interval(secs => p_window_seconds) THEN
            UPDATE public.auth_throttle_state
            SET attempts = 0, window_started_at = v_now, blocked_until = NULL, updated_at = v_now
            WHERE key_type = v_kind AND key_hash = v_key;
        ELSIF r.attempts >= p_max_attempts THEN
            v_blocked := true;
        END IF;
    END LOOP;
    RETURN NOT v_blocked;
END;
$$;

CREATE OR REPLACE FUNCTION public.auth_throttle_record_failure(
    p_ip_key text,
    p_email_key text,
    p_window_seconds integer,
    p_max_attempts integer,
    p_cooldown_seconds integer
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $$
DECLARE
    v_now timestamptz := now();
    v_key text;
    v_kind text;
BEGIN
    FOREACH v_kind IN ARRAY ARRAY['ip','email'] LOOP
        v_key := CASE WHEN v_kind = 'ip' THEN p_ip_key ELSE p_email_key END;
        IF v_key IS NULL OR v_key = '' THEN CONTINUE; END IF;
        INSERT INTO public.auth_throttle_state(key_hash,key_type,attempts,window_started_at,updated_at)
        VALUES(v_key,v_kind,1,v_now,v_now)
        ON CONFLICT (key_type,key_hash) DO UPDATE SET
            attempts = CASE
                WHEN v_now - auth_throttle_state.window_started_at >= make_interval(secs => p_window_seconds) THEN 1
                ELSE auth_throttle_state.attempts + 1
            END,
            window_started_at = CASE
                WHEN v_now - auth_throttle_state.window_started_at >= make_interval(secs => p_window_seconds) THEN v_now
                ELSE auth_throttle_state.window_started_at
            END,
            blocked_until = CASE
                WHEN (
                    CASE
                        WHEN v_now - auth_throttle_state.window_started_at >= make_interval(secs => p_window_seconds) THEN 1
                        ELSE auth_throttle_state.attempts + 1
                    END
                ) >= p_max_attempts THEN v_now + make_interval(secs => p_cooldown_seconds)
                ELSE auth_throttle_state.blocked_until
            END,
            updated_at = v_now;
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION public.auth_throttle_reset(p_ip_key text, p_email_key text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $$
BEGIN
    DELETE FROM public.auth_throttle_state
    WHERE (key_type = 'ip' AND key_hash = p_ip_key)
       OR (key_type = 'email' AND key_hash = p_email_key);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.auth_throttle_check(text,text,integer,integer) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.auth_throttle_record_failure(text,text,integer,integer,integer) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.auth_throttle_reset(text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.auth_throttle_check(text,text,integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.auth_throttle_record_failure(text,text,integer,integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.auth_throttle_reset(text,text) TO service_role;
