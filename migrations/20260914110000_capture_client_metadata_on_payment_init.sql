-- Persist browser IP/user-agent when create-intent records the initial
-- requires_payment_method state. Stripe webhooks do not carry browser metadata,
-- so later terminal attempts can safely fall back to public.payments.

CREATE OR REPLACE FUNCTION public.record_payment_attempt(p_order_id uuid, p_user_id uuid, p_pi_id text, p_amount numeric, p_status text, p_payment_method text DEFAULT NULL::text, p_error_code text DEFAULT NULL::text, p_error_message text DEFAULT NULL::text, p_ip_address text DEFAULT NULL::text, p_user_agent text DEFAULT NULL::text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE
  v_payment_id uuid; v_attempt integer; v_reservation_id uuid; v_reserved_attempt integer;
  v_policy_max integer; v_gateway jsonb; v_ip text; v_ua text;
BEGIN
  SELECT p.id,p.ip_address,p.user_agent INTO v_payment_id,v_ip,v_ua FROM public.payments p
  WHERE p.order_id=p_order_id ORDER BY p.created_at LIMIT 1 FOR UPDATE;
  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND'; END IF;
  v_ip:=COALESCE(NULLIF(TRIM(p_ip_address),''),v_ip);
  v_ua:=COALESCE(NULLIF(TRIM(p_user_agent),''),v_ua);

  IF p_status IN ('requires_payment_method','requires_confirmation','requires_action') THEN
    UPDATE public.payments SET ip_address=COALESCE(v_ip,ip_address),user_agent=COALESCE(v_ua,user_agent),updated_at=now() WHERE id=v_payment_id;
    RETURN;
  END IF;
  IF p_status='failed' AND p_payment_method IS NULL AND p_error_code IS NULL THEN RETURN; END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));
  SELECT greatest(1,coalesce(prp.max_attempts,5)) INTO v_policy_max FROM public.payment_retry_policy prp WHERE prp.id=true;
  v_policy_max:=greatest(1,coalesce(v_policy_max,5));
  SELECT r.id,r.attempt_number INTO v_reservation_id,v_reserved_attempt FROM public.payment_retry_reservations r
  WHERE r.order_id=p_order_id AND r.stripe_payment_intent_id=p_pi_id AND r.status='reserved' AND r.expires_at>now()
  ORDER BY r.created_at DESC LIMIT 1 FOR UPDATE;
  IF v_reservation_id IS NOT NULL THEN v_attempt:=v_reserved_attempt;
  ELSE SELECT COALESCE(MAX(a.attempt_number),0)+1 INTO v_attempt FROM public.payment_attempts a WHERE a.order_id=p_order_id; END IF;
  IF v_attempt>v_policy_max THEN RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',v_policy_max USING ERRCODE='P0001'; END IF;

  v_gateway:=jsonb_build_object('provider','stripe','payment_intent_id',p_pi_id,'order_id',p_order_id,'user_id',p_user_id,'amount',p_amount,'amount_paise',round(p_amount*100)::bigint,'currency','INR','status',p_status,'payment_method',p_payment_method,'error_code',p_error_code,'error_message',p_error_message,'record_type','payment_attempt');
  INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,payment_method,error_code,error_message,ip_address,user_agent,gateway_metadata,created_at,updated_at)
  VALUES(v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,p_amount,round(p_amount*100)::bigint,'INR',p_payment_method,p_error_code,p_error_message,v_ip,v_ua,v_gateway,now(),now());
  UPDATE public.payments SET status=p_status,payment_method=COALESCE(p_payment_method,payment_method),error_code=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_code END,error_message=CASE WHEN p_status='succeeded' THEN NULL ELSE p_error_message END,attempt_number=GREATEST(COALESCE(attempt_number,0),v_attempt),total_attempts=GREATEST(COALESCE(total_attempts,0),v_attempt),latest_attempt_number=v_attempt,latest_payment_intent_id=p_pi_id,successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,ip_address=COALESCE(v_ip,ip_address),user_agent=COALESCE(v_ua,user_agent),gateway_metadata=v_gateway,last_attempt_at=now(),updated_at=now() WHERE id=v_payment_id;
  IF v_reservation_id IS NOT NULL THEN UPDATE public.payment_retry_reservations SET status='consumed',consumed_at=COALESCE(consumed_at,now()) WHERE id=v_reservation_id AND status='reserved'; END IF;
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.record_payment_attempt(uuid,uuid,text,numeric,text,text,text,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid,uuid,text,numeric,text,text,text,text,text,text) TO service_role;
