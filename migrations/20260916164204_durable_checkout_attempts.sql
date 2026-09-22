-- Durable correlation boundary for the provider-before-order checkout window.
-- This migration was already applied to production as version 20260916164204.

CREATE TABLE IF NOT EXISTS public.checkout_payment_attempts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  idempotency_key uuid NOT NULL,
  payment_provider text NOT NULL,
  provider_payment_id text,
  amount_paise bigint NOT NULL CHECK (amount_paise > 0),
  currency text NOT NULL DEFAULT 'inr',
  status text NOT NULL DEFAULT 'provider_pending'
    CHECK (status IN ('provider_pending','provider_created','order_created','cancel_requested','cancelled','orphan_risk','completed')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 minutes'),
  last_error text,
  UNIQUE (customer_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_checkout_payment_attempts_reconcile
  ON public.checkout_payment_attempts(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_checkout_payment_attempts_provider_payment
  ON public.checkout_payment_attempts(payment_provider, provider_payment_id)
  WHERE provider_payment_id IS NOT NULL;

ALTER TABLE public.checkout_payment_attempts ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.create_checkout_payment_attempt(
  p_customer_id uuid,
  p_idempotency_key uuid,
  p_provider text,
  p_amount_paise bigint,
  p_currency text DEFAULT 'inr'
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE v_id uuid;
BEGIN
  INSERT INTO public.checkout_payment_attempts(
    customer_id,idempotency_key,payment_provider,amount_paise,currency
  )
  VALUES(
    p_customer_id,p_idempotency_key,lower(trim(p_provider)),
    p_amount_paise,lower(trim(p_currency))
  )
  ON CONFLICT(customer_id,idempotency_key)
  DO UPDATE SET updated_at=now()
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

CREATE OR REPLACE FUNCTION public.update_checkout_payment_attempt(
  p_id uuid,
  p_provider_payment_id text DEFAULT NULL,
  p_status text DEFAULT NULL,
  p_last_error text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
BEGIN
  UPDATE public.checkout_payment_attempts
  SET provider_payment_id = COALESCE(p_provider_payment_id, provider_payment_id),
      status = COALESCE(p_status, status),
      last_error = p_last_error,
      updated_at = now()
  WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Checkout payment attempt not found';
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.create_checkout_payment_attempt(uuid,uuid,text,bigint,text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.update_checkout_payment_attempt(uuid,text,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.create_checkout_payment_attempt(uuid,uuid,text,bigint,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.update_checkout_payment_attempt(uuid,text,text,text) TO service_role;

REVOKE ALL ON public.checkout_payment_attempts FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.checkout_payment_attempts TO service_role;
