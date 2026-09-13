-- Keep payment-attempt accounting bounded even if an application path
-- reaches record_payment_attempt without first reserving a retry slot.
-- Retry reservations remain the preferred orchestration path; this RPC is
-- the database-level safety net and never increments counters on rejection.

CREATE OR REPLACE FUNCTION public.record_payment_attempt(p_order_id uuid, p_user_id uuid, p_pi_id text, p_amount numeric, p_status text, p_payment_method text DEFAULT NULL::text, p_error_code text DEFAULT NULL::text, p_error_message text DEFAULT NULL::text, p_ip_address text DEFAULT NULL::text, p_user_agent text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_catalog', 'pg_temp'
AS $function$
DECLARE
 v_payment_id uuid;
 v_attempt_id uuid;
 v_attempt integer;
 v_reservation_id uuid;
 v_reserved_attempt integer;
 v_existing_status text;
 v_gateway jsonb;
 v_policy_max integer;
 v_payment_max integer;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));
 SELECT p.id,p.status,p.max_attempts INTO v_payment_id,v_existing_status,v_payment_max
 FROM public.payments p
 WHERE p.order_id=p_order_id
   AND (p.stripe_payment_intent_id=p_pi_id OR p.latest_payment_intent_id=p_pi_id)
 ORDER BY p.created_at LIMIT 1;
 IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND'; END IF;

 SELECT COALESCE(p.gateway_metadata,'{}'::jsonb) INTO v_gateway FROM public.payments p WHERE p.id=v_payment_id;
 SELECT greatest(1,coalesce(prp.max_attempts,5)) INTO v_policy_max
 FROM public.payment_retry_policy prp WHERE prp.id=true;
 v_policy_max:=greatest(1,coalesce(v_payment_max,v_policy_max,5));

 SELECT r.id,r.attempt_number INTO v_reservation_id,v_reserved_attempt
 FROM public.payment_retry_reservations r
 WHERE r.order_id=p_order_id AND r.user_id=p_user_id
   AND r.stripe_payment_intent_id=p_pi_id AND r.status='reserved' AND r.expires_at>now()
 ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;

 IF v_reservation_id IS NOT NULL THEN
   v_attempt:=v_reserved_attempt;
 ELSE
   SELECT pa.id,pa.attempt_number,pa.status INTO v_attempt_id,v_attempt,v_existing_status
   FROM public.payment_attempts pa
   WHERE pa.order_id=p_order_id AND pa.stripe_payment_intent_id=p_pi_id
   ORDER BY pa.attempt_number DESC,pa.created_at DESC LIMIT 1 FOR UPDATE;
   IF v_attempt_id IS NOT NULL THEN
     UPDATE public.payment_attempts pa SET
       status=p_status,payment_method=COALESCE(p_payment_method,pa.payment_method),
       error_code=COALESCE(p_error_code,pa.error_code),error_message=COALESCE(p_error_message,pa.error_message),
       ip_address=COALESCE(p_ip_address,pa.ip_address),user_agent=COALESCE(p_user_agent,pa.user_agent),
       amount=p_amount,amount_paise=ROUND(p_amount*100)::bigint,gateway_metadata=v_gateway,updated_at=now()
     WHERE pa.id=v_attempt_id;
   ELSE
     SELECT GREATEST(
       COALESCE((SELECT MAX(a.attempt_number) FROM public.payment_attempts a WHERE a.order_id=p_order_id),0),
       COALESCE((SELECT MAX(r.attempt_number) FROM public.payment_retry_reservations r WHERE r.order_id=p_order_id),0)
     )+1 INTO v_attempt;
     IF v_attempt>v_policy_max THEN
       RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING errcode='P0001';
     END IF;
   END IF;
 END IF;

 IF v_attempt_id IS NULL THEN
   INSERT INTO public.payment_attempts(
     payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,
     amount,amount_paise,currency,payment_method,error_code,error_message,
     ip_address,user_agent,gateway_metadata,created_at,updated_at
   ) VALUES(
     v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,
     p_amount,ROUND(p_amount*100)::bigint,'INR',p_payment_method,p_error_code,p_error_message,
     p_ip_address,p_user_agent,v_gateway,now(),now()
   ) RETURNING id INTO v_attempt_id;
 END IF;

 UPDATE public.payments p SET
   status=p_status,payment_method=COALESCE(p_payment_method,p.payment_method),
   error_code=COALESCE(p_error_code,p.error_code),error_message=COALESCE(p_error_message,p.error_message),
   attempt_number=GREATEST(COALESCE(p.attempt_number,0),v_attempt),
   total_attempts=GREATEST(COALESCE(p.total_attempts,0),v_attempt),
   latest_attempt_number=GREATEST(COALESCE(p.latest_attempt_number,0),v_attempt),
   latest_payment_intent_id=p_pi_id,
   successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE p.successful_attempt_number END,
   last_attempt_at=now(),updated_at=now()
 WHERE p.id=v_payment_id;

 IF v_reservation_id IS NOT NULL THEN
   UPDATE public.payment_retry_reservations r
   SET status='consumed',consumed_at=COALESCE(r.consumed_at,now())
   WHERE r.id=v_reservation_id;
 END IF;
END;
$function$;
