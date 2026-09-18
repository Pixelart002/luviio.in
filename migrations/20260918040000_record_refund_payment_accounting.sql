-- Record a successful provider refund in the internal payment record and
-- double-entry-style payment ledger. Idempotent for repeated webhook/retry paths.

CREATE OR REPLACE FUNCTION public.record_payment_refund(
    p_order_id uuid,
    p_provider text,
    p_provider_payment_id text,
    p_amount numeric,
    p_currency text DEFAULT 'INR',
    p_reference text DEFAULT NULL,
    p_metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public'
AS $function$
DECLARE
    v_payment public.payments%ROWTYPE;
    v_attempt integer;
    v_provider text;
    v_provider_payment_id text;
    v_currency text;
BEGIN
    v_provider := lower(nullif(trim(p_provider), ''));
    v_provider_payment_id := nullif(trim(p_provider_payment_id), '');
    v_currency := upper(coalesce(nullif(trim(p_currency), ''), 'INR'));

    IF p_order_id IS NULL OR v_provider IS NULL OR v_provider_payment_id IS NULL
       OR p_amount IS NULL OR p_amount <= 0 THEN
        RETURN 'REFUND_ACCOUNTING_DATA_INVALID';
    END IF;

    SELECT * INTO v_payment
      FROM public.payments
     WHERE order_id = p_order_id
       AND payment_provider = v_provider
       AND provider_payment_id = v_provider_payment_id
     ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
     LIMIT 1
     FOR UPDATE;

    IF NOT FOUND THEN
        RETURN 'PAYMENT_NOT_FOUND';
    END IF;

    IF round(v_payment.amount, 2) < round(p_amount, 2) THEN
        RETURN 'REFUND_AMOUNT_EXCEEDS_PAYMENT';
    END IF;

    UPDATE public.payments
       SET status = 'refunded',
           updated_at = now()
     WHERE id = v_payment.id;

    SELECT max(a.attempt_number) INTO v_attempt
      FROM public.payment_attempts a
     WHERE a.payment_id = v_payment.id;

    INSERT INTO public.payment_ledger(
        order_id, payment_id, provider, provider_payment_id, entry_type,
        direction, amount, amount_paise, currency, attempt_number,
        reference, metadata
    )
    VALUES(
        p_order_id, v_payment.id, v_provider, v_provider_payment_id,
        'payment_refunded', 'debit', p_amount, round(p_amount * 100)::bigint,
        v_currency, v_attempt, coalesce(p_reference, p_order_id::text),
        coalesce(p_metadata, '{}'::jsonb) || jsonb_build_object('source', 'payment_refund')
    )
    ON CONFLICT(provider, provider_payment_id, entry_type) DO NOTHING;

    RETURN 'REFUNDED_ACCOUNTED';
END;
$function$;

REVOKE EXECUTE ON FUNCTION public.record_payment_refund(uuid,text,text,numeric,text,text,jsonb)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.record_payment_refund(uuid,text,text,numeric,text,text,jsonb)
    TO service_role;