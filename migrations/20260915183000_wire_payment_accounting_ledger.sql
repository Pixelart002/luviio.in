-- Financial ledger is separate from payment-attempt telemetry.
-- Failed/requires_* attempts never create accounting entries.
-- Settlement creates exactly one payment_received credit per provider payment identity.

CREATE TABLE IF NOT EXISTS public.payment_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id uuid NOT NULL REFERENCES public.orders(id) ON DELETE RESTRICT,
  payment_id uuid REFERENCES public.payments(id) ON DELETE RESTRICT,
  provider text NOT NULL,
  provider_payment_id text NOT NULL,
  entry_type text NOT NULL,
  direction text NOT NULL,
  amount numeric(14,2) NOT NULL CHECK (amount >= 0),
  amount_paise bigint NOT NULL CHECK (amount_paise >= 0),
  currency text NOT NULL,
  attempt_number integer,
  reference text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS payment_ledger_provider_event_uq
  ON public.payment_ledger(provider, provider_payment_id, entry_type);
CREATE INDEX IF NOT EXISTS payment_ledger_order_idx
  ON public.payment_ledger(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS payment_ledger_created_idx
  ON public.payment_ledger(created_at DESC);

ALTER TABLE public.payment_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.payment_ledger FROM public, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.payment_ledger TO service_role;

CREATE OR REPLACE FUNCTION public.settle_payment_transaction(
  p_order_id uuid,
  p_provider text,
  p_provider_payment_id text,
  p_amount numeric,
  p_user_id uuid,
  p_payment_method text DEFAULT NULL,
  p_currency text DEFAULT NULL
)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public, pg_catalog, pg_temp
AS $function$
DECLARE
  v_order public.orders%ROWTYPE;
  v_existing public.payments%ROWTYPE;
  v_currency text;
  v_payment_id uuid;
  v_attempt integer;
BEGIN
  p_provider:=lower(nullif(trim(p_provider),''));
  p_provider_payment_id:=nullif(trim(p_provider_payment_id),'');
  v_currency:=upper(nullif(trim(p_currency),''));
  IF p_provider IS NULL OR p_provider_payment_id IS NULL THEN RETURN 'PAYMENT_IDENTITY_INVALID'; END IF;

  SELECT * INTO v_order FROM public.orders WHERE id=p_order_id AND customer_id=p_user_id FOR UPDATE;
  IF NOT FOUND THEN RETURN 'ORDER_NOT_FOUND'; END IF;
  IF v_order.status='paid' THEN RETURN 'ALREADY_PAID'; END IF;
  IF v_order.status='cancelled' THEN RETURN 'ORDER_ALREADY_CANCELLED'; END IF;
  IF p_amount IS NULL OR p_amount<=0 OR round(p_amount,2)<>round(v_order.total_amount,2) THEN RETURN 'PAYMENT_AMOUNT_MISMATCH'; END IF;
  IF v_currency IS NULL OR upper(coalesce(v_order.currency,''))<>v_currency THEN RETURN 'PAYMENT_CURRENCY_MISMATCH'; END IF;
  IF v_order.payment_provider IS NOT NULL AND lower(v_order.payment_provider)<>p_provider THEN RETURN 'PAYMENT_PROVIDER_MISMATCH'; END IF;
  IF v_order.provider_payment_id IS NOT NULL AND v_order.provider_payment_id<>p_provider_payment_id THEN RETURN 'PAYMENT_INTENT_MISMATCH'; END IF;

  SELECT * INTO v_existing FROM public.payments WHERE payment_provider=p_provider AND provider_payment_id=p_provider_payment_id LIMIT 1 FOR UPDATE;
  IF FOUND AND (v_existing.order_id<>p_order_id OR v_existing.user_id<>p_user_id) THEN RETURN 'PAYMENT_BINDING_MISMATCH'; END IF;

  INSERT INTO public.payments(order_id,user_id,stripe_payment_intent_id,payment_provider,provider_payment_id,amount,amount_paise,currency,status,payment_method,updated_at)
  VALUES(p_order_id,p_user_id,CASE WHEN p_provider='stripe' THEN p_provider_payment_id END,p_provider,p_provider_payment_id,p_amount,round(p_amount*100)::bigint,v_currency,'succeeded',p_payment_method,now())
  ON CONFLICT(payment_provider,provider_payment_id) DO UPDATE SET status='succeeded',amount=excluded.amount,amount_paise=excluded.amount_paise,currency=excluded.currency,payment_method=coalesce(excluded.payment_method,public.payments.payment_method),updated_at=now()
  RETURNING id INTO v_payment_id;

  SELECT max(a.attempt_number) INTO v_attempt FROM public.payment_attempts a WHERE a.payment_id=v_payment_id AND a.provider_payment_id=p_provider_payment_id;

  INSERT INTO public.payment_ledger(order_id,payment_id,provider,provider_payment_id,entry_type,direction,amount,amount_paise,currency,attempt_number,reference,metadata)
  VALUES(p_order_id,v_payment_id,p_provider,p_provider_payment_id,'payment_received','credit',p_amount,round(p_amount*100)::bigint,v_currency,v_attempt,p_order_id::text,jsonb_build_object('source','payment_settlement','payment_method',p_payment_method))
  ON CONFLICT(provider,provider_payment_id,entry_type) DO NOTHING;

  UPDATE public.orders SET status='paid',payment_provider=p_provider,provider_payment_id=p_provider_payment_id,stripe_payment_intent=CASE WHEN p_provider='stripe' THEN p_provider_payment_id ELSE stripe_payment_intent END,paid_at=coalesce(paid_at,now()) WHERE id=p_order_id;
  RETURN 'SETTLED';
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.settle_payment_transaction(uuid,text,text,numeric,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.settle_payment_transaction(uuid,text,text,numeric,uuid,text,text) TO service_role;