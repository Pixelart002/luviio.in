-- Repair live cleanup routine so maintenance telemetry reports actual deletions.
CREATE OR REPLACE FUNCTION private.cleanup_http_rate_limit_state()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'private'
AS $function$
DECLARE
    v_deleted integer;
BEGIN
    DELETE FROM private.http_rate_limit_state
    WHERE window_start < clock_timestamp() - interval '2 hours';

    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$function$;
