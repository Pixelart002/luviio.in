-- Same Stripe PaymentIntent retry architecture.
-- One canonical PI, atomic 5-attempt/60-second retry slots, and durable
-- attempt history. Superseded retry sessions are released; consumed retry
-- reservations correspond to an actual payment attempt.

DROP INDEX IF EXISTS public.payment_attempts_pi_id_unique;

CREATE TABLE IF NOT EXISTS public.payment_retry_reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id uuid NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
  user_id uuid NOT NULL,
  stripe_payment_intent_id text NOT NULL,
  attempt_number integer NOT NULL,
  status text NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved','consumed','released','expired')),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '120 seconds'),
  consumed_at timestamptz,
  released_at timestamptz
);

CREATE INDEX IF NOT EXISTS payment_retry_reservations_order_idx ON public.payment_retry_reservations(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS payment_retry_reservations_active_idx ON public.payment_retry_reservations(order_id, status, expires_at);

CREATE OR REPLACE FUNCTION public.reserve_payment_retry(p_order_id uuid, p_user_id uuid, p_pi_id text, p_window_seconds integer DEFAULT 60, p_max_attempts integer DEFAULT 5)
RETURNS TABLE(reservation_id uuid, attempt_number integer)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_made integer; v_issued integer; v_next integer; v_id uuid;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(p_order_id::text,0));
  UPDATE public.payment_retry_reservations SET status='expired',released_at=now()
  WHERE order_id=p_order_id AND status='reserved' AND expires_at<=now();
  SELECT count(*)::integer INTO v_made FROM public.payment_attempts
  WHERE order_id=p_order_id AND created_at>=now()-make_interval(secs=>p_window_seconds);
  SELECT count(*)::integer INTO v_issued FROM public.payment_retry_reservations
  WHERE order_id=p_order_id AND created_at>=now()-make_interval(secs=>p_window_seconds)
    AND status IN ('reserved','released','expired');
  IF v_made+v_issued>=p_max_attempts THEN
    RAISE EXCEPTION 'PAYMENT_RETRY_LIMIT:%',p_max_attempts USING ERRCODE='P0001';
  END IF;
  UPDATE public.payment_retry_reservations SET status='released',released_at=now()
  WHERE order_id=p_order_id AND status='reserved' AND expires_at>now();
  v_next:=v_made+v_issued+1;
  INSERT INTO public.payment_retry_reservations(order_id,user_id,stripe_payment_intent_id,attempt_number,status,created_at,expires_at)
  VALUES(p_order_id,p_user_id,p_pi_id,v_next,'reserved',now(),now()+interval '120 seconds')
  RETURNING id INTO v_id;
  RETURN QUERY SELECT v_id,v_next;
END;$function$;

CREATE OR REPLACE FUNCTION public.record_payment_attempt(
  p_order_id uuid, p_user_id uuid, p_pi_id text, p_amount numeric, p_status text,
  p_payment_method text DEFAULT NULL, p_error_code text DEFAULT NULL, p_error_message text DEFAULT NULL,
  p_ip_address text DEFAULT NULL, p_user_agent text DEFAULT NULL
)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'public','pg_catalog','pg_temp'
AS $function$
DECLARE v_payment_id uuid; v_attempt_id uuid; v_attempt integer; v_reservation_id uuid; v_reserved_attempt integer;
BEGIN
  SELECT id INTO v_payment_id FROM public.payments WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id LIMIT 1;
  IF v_payment_id IS NULL THEN SELECT id INTO v_payment_id FROM public.payments WHERE order_id=p_order_id LIMIT 1; END IF;
  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND'; END IF;
  SELECT id,attempt_number INTO v_reservation_id,v_reserved_attempt
  FROM public.payment_retry_reservations
  WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id AND status='reserved' AND expires_at>now()
  ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  IF v_reservation_id IS NOT NULL THEN
    v_attempt:=v_reserved_attempt;
    INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,error_message,created_at)
    VALUES(v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,p_amount,ROUND(p_amount*100)::bigint,'INR',p_error_message,now());
    UPDATE public.payment_retry_reservations SET status='consumed',consumed_at=now() WHERE id=v_reservation_id;
  ELSE
    SELECT id,attempt_number INTO v_attempt_id,v_attempt FROM public.payment_attempts
    WHERE order_id=p_order_id AND stripe_payment_intent_id=p_pi_id
      AND status IN ('requires_payment_method','requires_confirmation','requires_action','processing')
    ORDER BY attempt_number DESC,created_at DESC LIMIT 1;
    IF v_attempt_id IS NOT NULL THEN
      UPDATE public.payment_attempts SET status=p_status,error_message=p_error_message,amount=p_amount,amount_paise=ROUND(p_amount*100)::bigint WHERE id=v_attempt_id;
    ELSE
      SELECT COALESCE(MAX(attempt_number),0)+1 INTO v_attempt FROM public.payment_attempts WHERE order_id=p_order_id;
      INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,error_message,created_at)
      VALUES(v_payment_id,p_order_id,p_user_id,p_pi_id,v_attempt,p_status,p_amount,ROUND(p_amount*100)::bigint,'INR',p_error_message,now());
    END IF;
  END IF;
  UPDATE public.payments SET status=p_status,payment_method=COALESCE(p_payment_method,payment_method),error_code=COALESCE(p_error_code,error_code),error_message=COALESCE(p_error_message,error_message),attempt_number=v_attempt,total_attempts=GREATEST(COALESCE(total_attempts,0),v_attempt),latest_attempt_number=v_attempt,latest_payment_intent_id=p_pi_id,successful_attempt_number=CASE WHEN p_status='succeeded' THEN v_attempt ELSE successful_attempt_number END,last_attempt_at=now(),updated_at=now() WHERE id=v_payment_id;
END;$function$;

CREATE OR REPLACE FUNCTION public.trg_track_payment_retry()
RETURNS trigger LANGUAGE plpgsql
AS $function$
DECLARE v_reservation_id uuid; v_reserved_attempt integer; v_attempt_id uuid; v_attempt integer;
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status='succeeded' THEN
    SELECT id,attempt_number INTO v_reservation_id,v_reserved_attempt
    FROM public.payment_retry_reservations
    WHERE order_id=NEW.order_id AND stripe_payment_intent_id=NEW.stripe_payment_intent_id AND status='reserved' AND expires_at>now()
    ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
    IF v_reservation_id IS NOT NULL THEN
      v_attempt:=v_reserved_attempt;
      INSERT INTO public.payment_attempts(payment_id,order_id,user_id,stripe_payment_intent_id,attempt_number,status,amount,amount_paise,currency,created_at)
      VALUES(NEW.id,NEW.order_id,NEW.user_id,NEW.stripe_payment_intent_id,v_attempt,'succeeded',NEW.amount,NEW.amount_paise,NEW.currency,now());
      UPDATE public.payment_retry_reservations SET status='consumed',consumed_at=now() WHERE id=v_reservation_id;
      NEW.attempt_number:=v_attempt; NEW.total_attempts:=GREATEST(COALESCE(NEW.total_attempts,0),v_attempt); NEW.latest_attempt_number:=v_attempt; NEW.successful_attempt_number:=v_attempt;
    ELSE
      SELECT id,attempt_number INTO v_attempt_id,v_attempt FROM public.payment_attempts
      WHERE order_id=NEW.order_id AND stripe_payment_intent_id=NEW.stripe_payment_intent_id
      ORDER BY attempt_number DESC,created_at DESC LIMIT 1;
      IF v_attempt_id IS NOT NULL THEN
        UPDATE public.payment_attempts SET status='succeeded',amount=NEW.amount,amount_paise=NEW.amount_paise WHERE id=v_attempt_id;
        NEW.attempt_number:=v_attempt; NEW.total_attempts:=GREATEST(COALESCE(NEW.total_attempts,0),v_attempt); NEW.latest_attempt_number:=v_attempt; NEW.successful_attempt_number:=v_attempt;
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;$function$;

DROP TRIGGER IF EXISTS trg_track_payment_retry ON public.payments;
CREATE TRIGGER trg_track_payment_retry BEFORE UPDATE OF status ON public.payments FOR EACH ROW EXECUTE FUNCTION public.trg_track_payment_retry();

REVOKE ALL ON FUNCTION public.reserve_payment_retry(uuid,uuid,text,integer,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.reserve_payment_retry(uuid,uuid,text,integer,integer) TO service_role;
