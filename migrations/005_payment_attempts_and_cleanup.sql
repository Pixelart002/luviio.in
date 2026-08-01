-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 005: payment_attempts audit table + stale-code cleanup
-- ═══════════════════════════════════════════════════════════════════════════
-- Context: running migration 004 created a NEW `cancel_order_and_release_stock`
-- with signature (uuid, text). Postgres treats a function with a different
-- argument list as a DIFFERENT OVERLOAD, not a replacement -- so the OLD
-- (uuid)-only version kept existing side-by-side. That's the "2 functions,
-- don't know which one runs" confusion. Fixed below (section 1).
--
-- This migration also adds a proper Amazon-style payment_attempts audit log:
--   * `payments` gets attempt_number (auto-assigned, 1st/2nd/3rd try on this
--     order), ip_address, user_agent.
--   * `payment_attempts` is an APPEND-ONLY log -- every meaningful status
--     change on a `payments` row (create / fail / succeed / cancel) writes
--     one new row here automatically via a trigger. Nothing in the Python
--     code has to remember to log an attempt -- it happens at the DB layer
--     no matter which code path touches `payments`.
-- Safe to run multiple times.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. STALE CODE: drop the old 1-arg overload ───────────────────────────
-- After this, only cancel_order_and_release_stock(uuid, text) exists.
DROP FUNCTION IF EXISTS public.cancel_order_and_release_stock(uuid);

-- ── 2. payments: attempt tracking + request metadata ─────────────────────
ALTER TABLE public.payments
  ADD COLUMN IF NOT EXISTS attempt_number int,
  ADD COLUMN IF NOT EXISTS ip_address     text,
  ADD COLUMN IF NOT EXISTS user_agent     text;

-- Auto-assign attempt_number the moment a new payments row is created
-- (i.e. every fresh PaymentIntent -- first try or a retry). Never
-- recomputed on UPDATE, so a row keeps the attempt number it was born with.
CREATE OR REPLACE FUNCTION public.fn_assign_payment_attempt_number()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.attempt_number IS NULL THEN
        SELECT COUNT(*) + 1 INTO NEW.attempt_number
          FROM public.payments
         WHERE order_id = NEW.order_id;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_assign_payment_attempt_number ON public.payments;
CREATE TRIGGER trg_assign_payment_attempt_number
    BEFORE INSERT ON public.payments
    FOR EACH ROW EXECUTE FUNCTION public.fn_assign_payment_attempt_number();

-- ── 3. payment_attempts: append-only audit log ───────────────────────────
CREATE TABLE IF NOT EXISTS public.payment_attempts (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                 uuid NOT NULL REFERENCES public.orders(id),
    user_id                  uuid,
    stripe_payment_intent_id text NOT NULL,
    attempt_number           int NOT NULL,
    status                   text NOT NULL,
    amount                   numeric,
    amount_paise             bigint,
    currency                 text DEFAULT 'INR',
    payment_method           text,
    failure_code             text,
    failure_reason           text,
    ip_address               text,
    user_agent               text,
    recorded_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payment_attempts_order_id ON public.payment_attempts(order_id);
CREATE INDEX IF NOT EXISTS idx_payment_attempts_user_id  ON public.payment_attempts(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_attempts_pi_id    ON public.payment_attempts(stripe_payment_intent_id);

-- Auto-log every real status change on `payments` (skips no-op updates that
-- don't actually change status, so retrying the same upsert twice doesn't
-- spam duplicate log rows).
CREATE OR REPLACE FUNCTION public.fn_log_payment_attempt()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.payment_attempts (
        order_id, user_id, stripe_payment_intent_id, attempt_number,
        status, amount, amount_paise, currency, payment_method,
        failure_code, failure_reason, ip_address, user_agent
    ) VALUES (
        NEW.order_id, NEW.user_id, NEW.stripe_payment_intent_id, NEW.attempt_number,
        NEW.status, NEW.amount, NEW.amount_paise, NEW.currency, NEW.payment_method,
        NEW.failure_code, NEW.failure_reason, NEW.ip_address, NEW.user_agent
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_log_payment_attempt ON public.payments;
CREATE TRIGGER trg_log_payment_attempt
    AFTER INSERT OR UPDATE ON public.payments
    FOR EACH ROW EXECUTE FUNCTION public.fn_log_payment_attempt();