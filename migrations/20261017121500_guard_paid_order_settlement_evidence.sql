BEGIN;

-- A paid order must have a matching successful payment AND an accounting credit.
-- This protects every writer (API, RPC, admin tooling, and direct service-role SQL),
-- while leaving historical rows untouched. Settlement routines already write the
-- payment row and ledger credit before transitioning the order to paid.
CREATE OR REPLACE FUNCTION public.guard_order_paid_requires_settlement()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
  v_amount_paise bigint;
BEGIN
  IF NEW.status = 'paid' AND (TG_OP = 'INSERT' OR OLD.status IS DISTINCT FROM 'paid') THEN
    v_amount_paise := round(NEW.total_amount * 100)::bigint;

    IF NOT EXISTS (
      SELECT 1
        FROM public.payments p
        JOIN public.payment_ledger l
          ON l.order_id = p.order_id
         AND l.payment_id = p.id
         AND lower(l.provider) = lower(p.payment_provider)
         AND l.provider_payment_id = coalesce(
               nullif(trim(p.provider_payment_id), ''),
               nullif(trim(p.stripe_payment_intent_id), '')
             )
       WHERE p.order_id = NEW.id
         AND lower(coalesce(p.status, '')) = 'succeeded'
         AND round(p.amount * 100)::bigint = v_amount_paise
         AND p.amount_paise = v_amount_paise
         AND l.entry_type = 'payment_received'
         AND l.direction = 'credit'
         AND l.amount_paise = v_amount_paise
    ) THEN
      RAISE EXCEPTION USING
        ERRCODE = '23514',
        MESSAGE = 'ORDER_PAID_REQUIRES_SETTLED_PAYMENT',
        DETAIL = 'A successful payment record and matching payment_received ledger credit are required before an order can become paid.';
    END IF;

    -- Stripe must always have an identity. Any identity supplied by another
    -- provider must also match; COD without a provider transaction ID uses its
    -- separate collection/settlement evidence and still needs the ledger above.
    IF lower(coalesce(NEW.payment_provider, '')) = 'stripe'
       OR nullif(trim(NEW.provider_payment_id), '') IS NOT NULL
       OR nullif(trim(NEW.stripe_payment_intent), '') IS NOT NULL THEN
      IF NOT EXISTS (
        SELECT 1
          FROM public.payments p
         WHERE p.order_id = NEW.id
           AND lower(coalesce(p.status, '')) = 'succeeded'
           AND (
             (
               nullif(trim(NEW.provider_payment_id), '') IS NOT NULL
               AND nullif(trim(NEW.provider_payment_id), '') =
                 coalesce(nullif(trim(p.provider_payment_id), ''), nullif(trim(p.stripe_payment_intent_id), ''))
             )
             OR (
               lower(coalesce(NEW.payment_provider, '')) = 'stripe'
               AND nullif(trim(NEW.stripe_payment_intent), '') IS NOT NULL
               AND nullif(trim(NEW.stripe_payment_intent), '') =
                 coalesce(nullif(trim(p.stripe_payment_intent_id), ''), nullif(trim(p.provider_payment_id), ''))
             )
           )
      ) THEN
        RAISE EXCEPTION USING
          ERRCODE = '23514',
          MESSAGE = 'ORDER_PAID_PROVIDER_IDENTITY_MISMATCH',
          DETAIL = 'The order provider identity must match the successful payment record.';
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$function$;

DROP TRIGGER IF EXISTS zz_guard_order_paid_requires_settlement ON public.orders;
DROP TRIGGER IF EXISTS zz_guard_order_paid_requires_settlement_insert ON public.orders;
CREATE TRIGGER zz_guard_order_paid_requires_settlement_insert
BEFORE INSERT ON public.orders
FOR EACH ROW
EXECUTE FUNCTION public.guard_order_paid_requires_settlement();
CREATE TRIGGER zz_guard_order_paid_requires_settlement
BEFORE UPDATE OF status ON public.orders
FOR EACH ROW
EXECUTE FUNCTION public.guard_order_paid_requires_settlement();

REVOKE ALL ON FUNCTION public.guard_order_paid_requires_settlement() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.guard_order_paid_requires_settlement() TO service_role;

COMMIT;
