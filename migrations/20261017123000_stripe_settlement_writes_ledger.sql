BEGIN;

-- Preserve the deployed 8-argument RPC signature and attempt recorder, while
-- making successful Stripe settlement ledger-backed before the paid transition.
CREATE OR REPLACE FUNCTION public.settle_order_transaction(
  p_order_id uuid,
  p_pi_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL::text,
  p_stripe_currency text DEFAULT NULL::text,
  p_ip_address text DEFAULT NULL::text,
  p_user_agent text DEFAULT NULL::text
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog','public'
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_currency text;
  v_bound_order uuid;
  v_bound_user uuid;
  v_payment_id uuid;
  v_attempt integer;
BEGIN
  SELECT * INTO v_order
    FROM public.orders
   WHERE id=p_order_id AND customer_id=p_user_id
   FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'PAYMENT_ORDER_NOT_FOUND'; END IF;
  IF v_order.status='paid' THEN RETURN 'ALREADY_PAID'; END IF;
  IF v_order.status='cancelled' THEN RETURN 'ORDER_ALREADY_CANCELLED'; END IF;
  IF p_amount IS NULL OR p_amount<=0 OR v_order.total_amount IS NULL
     OR round(p_amount,2)<>round(v_order.total_amount,2) THEN
    RAISE EXCEPTION 'PAYMENT_AMOUNT_MISMATCH';
  END IF;

  v_currency:=upper(trim(coalesce(v_order.currency,'')));
  IF v_currency<>'INR' THEN RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF p_stripe_currency IS NOT NULL AND upper(trim(p_stripe_currency))<>v_currency THEN
    RAISE EXCEPTION 'PAYMENT_CURRENCY_MISMATCH';
  END IF;
  IF v_order.stripe_payment_intent IS NOT NULL AND v_order.stripe_payment_intent<>p_pi_id THEN
    RAISE EXCEPTION 'PAYMENT_INTENT_MISMATCH';
  END IF;

  SELECT p.order_id,p.user_id INTO v_bound_order,v_bound_user
    FROM public.payments p
   WHERE p.stripe_payment_intent_id=p_pi_id
      OR (p.order_id=p_order_id AND p.latest_payment_intent_id=p_pi_id)
      OR (p.payment_provider='stripe' AND p.provider_payment_id=p_pi_id)
   ORDER BY p.created_at
   LIMIT 1;
  IF v_bound_order IS NOT NULL AND (v_bound_order<>p_order_id OR v_bound_user<>p_user_id) THEN
    RAISE EXCEPTION 'PAYMENT_BINDING_MISMATCH';
  END IF;

  -- Existing durable attempt logic remains authoritative for retries and telemetry.
  PERFORM public.record_payment_attempt(
    p_order_id,p_user_id,p_pi_id,p_amount,'succeeded',p_payment_method,
    NULL,NULL,p_ip_address,p_user_agent
  );

  SELECT p.id,COALESCE(p.successful_attempt_number,p.latest_attempt_number,p.attempt_number,1)
    INTO v_payment_id,v_attempt
    FROM public.payments p
   WHERE p.order_id=p_order_id
     AND (p.provider_payment_id=p_pi_id OR p.stripe_payment_intent_id=p_pi_id OR p.latest_payment_intent_id=p_pi_id)
   ORDER BY p.created_at DESC
   LIMIT 1
   FOR UPDATE;
  IF v_payment_id IS NULL THEN RAISE EXCEPTION 'PAYMENT_RECORD_NOT_FOUND'; END IF;

  UPDATE public.payments
     SET payment_provider='stripe',
         provider_payment_id=p_pi_id,
         stripe_payment_intent_id=p_pi_id,
         amount=p_amount,
         amount_paise=round(p_amount*100)::bigint,
         currency=v_currency,
         status='succeeded',
         payment_method=coalesce(p_payment_method,payment_method),
         error_code=NULL,
         error_message=NULL,
         updated_at=now()
   WHERE id=v_payment_id;

  -- Unique provider identity makes Stripe webhook retries idempotent.
  INSERT INTO public.payment_ledger(
    order_id,payment_id,provider,provider_payment_id,entry_type,direction,
    amount,amount_paise,currency,attempt_number,reference,metadata
  )
  VALUES(
    p_order_id,v_payment_id,'stripe',p_pi_id,'payment_received','credit',
    p_amount,round(p_amount*100)::bigint,v_currency,v_attempt,p_pi_id,
    jsonb_build_object(
      'source','stripe_webhook_settlement',
      'payment_method',coalesce(p_payment_method,'card')
    )
  )
  ON CONFLICT (provider,provider_payment_id,entry_type)
    WHERE entry_type <> 'payment_refunded'
    DO NOTHING;

  -- Paid-order guard sees the succeeded payment and matching ledger credit.
  UPDATE public.orders
     SET status='paid',
         stripe_payment_intent=p_pi_id,
         payment_provider='stripe',
         provider_payment_id=p_pi_id,
         paid_at=coalesce(paid_at,now()),
         payment_method=coalesce(p_payment_method,'card')
   WHERE id=p_order_id;

  IF v_order.coupon_id IS NOT NULL THEN
    IF NOT public.record_coupon_redemption(
      v_order.coupon_id,p_user_id,p_order_id,coalesce(v_order.discount_amount,0)
    ) THEN RAISE EXCEPTION 'COUPON_REDEMPTION_FAILED'; END IF;
  END IF;
  RETURN 'SETTLED';
END;
$function$;

COMMIT;
