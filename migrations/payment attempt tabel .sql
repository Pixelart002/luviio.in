-- ============================================================================
-- Migration: payment_attempts + payments summary hardening
-- ============================================================================

-- 1) Payment attempts history table
CREATE TABLE IF NOT EXISTS public.payment_attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Relations
    payment_id uuid NOT NULL REFERENCES public.payments(id) ON DELETE CASCADE,
    order_id uuid NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    user_id uuid REFERENCES public.users(id) ON DELETE SET NULL,

    -- Sequence
    attempt_number integer NOT NULL,

    -- Stripe / gateway IDs
    stripe_payment_intent_id text NOT NULL,
    stripe_charge_id text,
    stripe_balance_transaction_id text,
    stripe_event_id text,
    stripe_refund_id text,

    -- State
    status text NOT NULL CHECK (
        status IN (
            'requires_payment_method',
            'requires_confirmation',
            'requires_action',
            'processing',
            'succeeded',
            'failed',
            'cancelled',
            'refunded',
            'succeeded_orphaned'
        )
    ),

    -- Money
    amount numeric(12,2) NOT NULL,
    amount_paise bigint NOT NULL,
    currency text NOT NULL DEFAULT 'INR',

    -- Payment method detail
    payment_method text,
    payment_method_type text,
    card_brand text,
    card_last4 text,
    card_country text,
    wallet_type text,

    -- Failure detail
    failure_code text,
    failure_reason text,
    decline_code text,

    -- Risk / auth
    risk_level text,
    risk_score numeric(6,2),
    three_ds_required boolean DEFAULT false,
    three_ds_result text,

    -- Retry / refund
    retryable boolean DEFAULT true,
    retry_reason text,
    refunded boolean DEFAULT false,
    refunded_amount numeric(12,2),
    refunded_at timestamptz,

    -- Timing
    initiated_at timestamptz,
    authorized_at timestamptz,
    captured_at timestamptz,
    failed_at timestamptz,
    cancelled_at timestamptz,

    -- Raw gateway payloads
    gateway_request jsonb,
    gateway_response jsonb,
    gateway_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- Audit
    ip_address inet,
    user_agent text,
    device_id text,
    source text,

    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_payment_attempt_pi UNIQUE (stripe_payment_intent_id),
    CONSTRAINT uq_payment_attempt_order_no UNIQUE (order_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_payment_id
    ON public.payment_attempts(payment_id);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_order_id
    ON public.payment_attempts(order_id);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_user_id
    ON public.payment_attempts(user_id);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_status
    ON public.payment_attempts(status);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_created_at
    ON public.payment_attempts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_pi
    ON public.payment_attempts(stripe_payment_intent_id);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_charge
    ON public.payment_attempts(stripe_charge_id);

-- 2) Auto-touch updated_at trigger
CREATE OR REPLACE FUNCTION public.fn_touch_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_payment_attempts_touch_updated_at ON public.payment_attempts;
CREATE TRIGGER trg_payment_attempts_touch_updated_at
BEFORE UPDATE ON public.payment_attempts
FOR EACH ROW
EXECUTE FUNCTION public.fn_touch_updated_at();

-- 3) Optional but recommended: add summary fields to payments
ALTER TABLE public.payments
    ADD COLUMN IF NOT EXISTS latest_attempt_number integer,
    ADD COLUMN IF NOT EXISTS successful_attempt_number integer,
    ADD COLUMN IF NOT EXISTS total_attempts integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS latest_payment_intent_id text,
    ADD COLUMN IF NOT EXISTS first_attempt_at timestamptz,
    ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_payments_order_id
    ON public.payments(order_id);

CREATE INDEX IF NOT EXISTS idx_payments_latest_pi
    ON public.payments(latest_payment_intent_id);