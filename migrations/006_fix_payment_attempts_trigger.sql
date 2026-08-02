-- ============================================================================
-- Migration 006: Fix fn_log_payment_attempt trigger to include payment_id
-- ============================================================================
-- Root cause: Migration 005 created fn_log_payment_attempt without payment_id
-- in its INSERT into payment_attempts. A later migration added
-- payment_id uuid NOT NULL to payment_attempts, but the trigger was never
-- updated to supply it, causing a NOT NULL constraint violation on every
-- INSERT/UPDATE to the payments table.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.fn_log_payment_attempt()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;

    INSERT INTO public.payment_attempts (
        payment_id, order_id, user_id, stripe_payment_intent_id, attempt_number,
        status, amount, amount_paise, currency, payment_method,
        failure_code, failure_reason, ip_address, user_agent
    ) VALUES (
        NEW.id, NEW.order_id, NEW.user_id, NEW.stripe_payment_intent_id, NEW.attempt_number,
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