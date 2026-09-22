-- Authoritative payment retry policy + durable per-order attempt history.
-- max_attempts is persisted in DB; total_attempts is attempts made.

CREATE TABLE IF NOT EXISTS public.payment_retry_policy (id boolean PRIMARY KEY DEFAULT true CHECK (id), max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts > 0 AND max_attempts <= 100), window_seconds integer NOT NULL DEFAULT 180 CHECK (window_seconds > 0), updated_at timestamptz NOT NULL DEFAULT now());
INSERT INTO public.payment_retry_policy(id,max_attempts,window_seconds) VALUES (true,5,180) ON CONFLICT (id) DO NOTHING;
ALTER TABLE public.payments ADD COLUMN IF NOT EXISTS max_attempts integer;
UPDATE public.payments SET max_attempts=5 WHERE max_attempts IS NULL OR max_attempts<=0;
ALTER TABLE public.payments ALTER COLUMN max_attempts SET DEFAULT 5;
ALTER TABLE public.payments ALTER COLUMN max_attempts SET NOT NULL;
ALTER TABLE public.payment_attempts ADD COLUMN IF NOT EXISTS payment_method text, ADD COLUMN IF NOT EXISTS error_code text, ADD COLUMN IF NOT EXISTS gateway_metadata jsonb NOT NULL DEFAULT '{}'::jsonb, ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS idx_payment_attempts_order_attempt_created ON public.payment_attempts(order_id,attempt_number,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_attempts_pi_created ON public.payment_attempts(stripe_payment_intent_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payment_retry_reservations_order_attempt ON public.payment_retry_reservations(order_id,attempt_number,created_at DESC);

CREATE OR REPLACE FUNCTION public.reserve_payment_retry(p_order_id uuid,p_user_id uuid,p_pi_id text,p_window_seconds integer DEFAULT NULL,p_max_attempts integer DEFAULT NULL)
RETURNS TABLE(reservation_id uuid,attempt_number integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_policy_max integer; v_policy_window integer; v_payment_id uuid; v_payment_status text; v_payment_max integer; v_existing uuid; v_existing_attempt integer; v_next integer; v_id uuid; v_expired record;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));
 SELECT max_attempts,window_seconds INTO v_policy_max,v_policy_window FROM public.payment_retry_policy WHERE id=true;
 v_policy_max:=COALESCE(p_max_attempts,v_policy_max,5); v_policy_window:=COALESCE(p_window_seconds,v_policy_window,180);
 SELECT p.id,p.status,p.max_attempts INTO v_payment_id,v_payment_status,v_payment_max FROM public.payments p WHERE p.order_id=p_order_id AND (p.stripe_payment_intent_id=p_pi_id OR p.latest_payment_intent_id=p_pi_id) ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE;
 IF v_payment_id IS NULL THEN SELECT p.id,p.status,p.max_attempts INTO v_payment_id,v_payment_status,v_payment_max FROM public.payments p WHERE p.order_id=p_order_id ORDER BY p.created_at DESC LIMIT 1 FOR UPDATE; END IF;
 IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_NOT_FOUND'; END IF;
 IF v_payment_status='succeeded' THEN RAISE EXCEPTION 'PAYMENT_ALREADY_SUCCEEDED' USING ERRCODE='P0001'; END IF;
 v_policy_max:=COALESCE(v_payment_max,v_policy_max,5);
 FOR v_expired IN SELECT r.* FROM public.payment_retry_reservations r WHERE r.order_id=p_order_id AND r.status='reserved' AND r.expires_at<=now() ORDER BY r.created_at FOR UPDATE LOOP
   IF NOT EXISTS (SELECT 1 FROM public.payment_attempts a WHERE a.order_id=v_expired.order_id AND a.attempt_number=v_expired.attempt_number) THEN
     INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,payment_method,error_message,gateway_metadata,created_at,updated_at)
     SELECT p.id,p.order_id,p.user_id,v_expired.stripe_payment_intent_id,v_expired.attempt_number,'expired',p.amount,p.amount_paise,p.currency,p.payment_method,'Payment retry reservation expired.',COALESCE(p.gateway_metadata,'{}'::jsonb),v_expired.expires_at,now() FROM public.payments p WHERE p.id=v_payment_id;
   END IF;
   UPDATE public.payment_retry_reservations SET status='expired',released_at=COALESCE(released_at,now()) WHERE id=v_expired.id;
 END LOOP;
 SELECT r.id,r.attempt_number INTO v_existing,v_existing_attempt FROM public.payment_retry_reservations r WHERE r.order_id=p_order_id AND r.user_id=p_user_id AND r.status='reserved' AND r.expires_at>now() ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;
 IF v_existing IS NOT NULL THEN
   UPDATE public.payments p SET attempt_number=GREATEST(COALESCE(p.attempt_number,0),v_existing_attempt),total_attempts=GREATEST(COALESCE(p.total_attempts,0),v_existing_attempt),latest_attempt_number=GREATEST(COALESCE(p.latest_attempt_number,0),v_existing_attempt),max_attempts=v_policy_max,latest_payment_intent_id=p_pi_id,last_attempt_at=now(),updated_at=now() WHERE p.id=v_payment_id;
   RETURN QUERY SELECT v_existing,v_existing_attempt; RETURN;
 END IF;
 SELECT GREATEST(COALESCE((SELECT MAX(a.attempt_number) FROM public.payment_attempts a WHERE a.order_id=p_order_id),0),COALESCE((SELECT MAX(r.attempt_number) FROM public.payment_retry_reservations r WHERE r.order_id=p_order_id),0))+1 INTO v_next;
 IF v_next>v_policy_max THEN RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING ERRCODE='P0001'; END IF;
 INSERT INTO public.payment_retry_reservations(order_id,user_id,stripe_payment_intent_id,attempt_number,status,created_at,expires_at) VALUES(p_order_id,p_user_id,p_pi_id,v_next,'reserved',now(),now()+make_interval(secs=>v_policy_window)) RETURNING id INTO v_id;
 UPDATE public.payments p SET attempt_number=v_next,total_attempts=v_next,latest_attempt_number=v_next,max_attempts=v_policy_max,latest_payment_intent_id=p_pi_id,last_attempt_at=now(),updated_at=now() WHERE p.id=v_payment_id;
 RETURN QUERY SELECT v_id,v_next;
END;$function$;

DROP FUNCTION IF EXISTS public.admin_payment_telemetry(integer,integer);
CREATE FUNCTION public.admin_payment_telemetry(p_limit integer,p_offset integer)
RETURNS TABLE(id uuid,order_id uuid,amount numeric,amount_paise bigint,currency text,status text,payment_method text,error_code text,error_message text,attempt_number integer,max_attempts integer,stripe_payment_intent_id text,created_at timestamptz,updated_at timestamptz,order_number text,order_status text,total_amount numeric,total_count bigint)
LANGUAGE sql SECURITY DEFINER SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
WITH durable_attempts AS (
 SELECT pa.id,pa.order_id,pa.amount,pa.amount_paise,pa.currency,pa.status,COALESCE(pa.payment_method,p.payment_method,o.payment_method,'card') payment_method,pa.error_code,pa.error_message,pa.attempt_number,COALESCE(p.max_attempts,5) max_attempts,pa.stripe_payment_intent_id::text,pa.created_at,pa.updated_at,o.order_number,o.status,o.total_amount
 FROM public.payment_attempts pa LEFT JOIN public.payments p ON p.id=pa.payment_id AND p.order_id=pa.order_id LEFT JOIN public.orders o ON o.id=pa.order_id
), expired_slots AS (
 SELECT r.id,r.order_id,COALESCE(p.amount,o.total_amount,0)::numeric,ROUND(COALESCE(p.amount,o.total_amount,0)*100)::bigint,COALESCE(p.currency,o.currency,'INR')::text,'expired'::text,COALESCE(p.payment_method,o.payment_method,'card')::text,NULL::text,'Payment retry reservation expired.'::text,r.attempt_number,COALESCE(p.max_attempts,5)::integer,r.stripe_payment_intent_id::text,r.created_at,COALESCE(r.released_at,r.expires_at,r.created_at),o.order_number,o.status,o.total_amount
 FROM public.payment_retry_reservations r LEFT JOIN public.payments p ON p.order_id=r.order_id LEFT JOIN public.orders o ON o.id=r.order_id
 WHERE r.status='expired' AND NOT EXISTS(SELECT 1 FROM public.payment_attempts pa WHERE pa.order_id=r.order_id AND pa.attempt_number=r.attempt_number)
), cod_rows AS (
 SELECT o.id,o.id,o.total_amount,ROUND(o.total_amount*100)::bigint,COALESCE(o.currency,'INR'),'pending'::text,'cod'::text,NULL::text,NULL::text,1,COALESCE((SELECT max_attempts FROM public.payment_retry_policy WHERE id=true),5)::integer,NULL::text,o.created_at,o.updated_at,o.order_number,o.status,o.total_amount
 FROM public.orders o WHERE o.payment_method='cod' AND NOT EXISTS(SELECT 1 FROM public.payments p WHERE p.order_id=o.id) AND NOT EXISTS(SELECT 1 FROM public.payment_attempts pa WHERE pa.order_id=o.id)
), events AS (SELECT * FROM durable_attempts UNION ALL SELECT * FROM expired_slots UNION ALL SELECT * FROM cod_rows)
SELECT e.*,COUNT(*) OVER() FROM events e ORDER BY e.created_at DESC,e.attempt_number DESC,e.order_number DESC,e.id DESC LIMIT LEAST(GREATEST(p_limit,1),50) OFFSET GREATEST(p_offset,0);
$function$;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry(uuid,uuid,text,integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.admin_payment_telemetry(integer,integer) TO service_role;