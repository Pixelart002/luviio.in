-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 004: Payment / Order Lifecycle Hardening
-- ═══════════════════════════════════════════════════════════════════════════
-- Fixes, in order:
--   1. orders/payments get updated_at (+ orders gets cancelled_at) with
--      auto-touch triggers, so every mutation is timestamped consistently.
--   2. payments gets failure_reason/failure_code so a failed attempt is a
--      first-class, queryable record -- not just a log line.
--   3. stripe_webhook_events -- idempotency ledger so a Stripe webhook
--      retry can never be processed twice.
--   4. settle_order_transaction -- FIXED. Two bugs removed:
--        a) "ON CONFLICT ... DO NOTHING" meant that once we start writing a
--           payments row at intent-creation time, a real success would
--           never overwrite the earlier 'requires_payment_method' row.
--           Now it's DO UPDATE.
--        b) It used to silently flip a CANCELLED/REFUNDED order back to
--           'paid' if a late Stripe confirmation arrived after the
--           abandoned-checkout sweep had already released the stock.
--           Now that path is blocked and flagged for auto-refund instead.
--   5. cancel_order_and_release_stock -- MERGED "Gemini" (timestamps +
--      cancellation note) + "Sentry" (stock audit + terminal-state guard)
--      versions, kept row locking + idempotency from both, added a
--      product-row lock (FOR UPDATE OF p) so two cancellations touching
--      the same SKU can't race each other, and now also marks any
--      still-open payments rows for the order as 'cancelled'.
--   6. mark_payment_failed -- NEW. Records a failed attempt without ever
--      downgrading a row that's already 'succeeded'/'refunded' (guards
--      against Stripe's at-least-once, not-guaranteed-order webhook
--      delivery reordering events on you).
-- Safe to run multiple times (IF NOT EXISTS / CREATE OR REPLACE throughout).
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. Schema additions ──────────────────────────────────────────────────
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS updated_at   timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;

ALTER TABLE public.payments
  ADD COLUMN IF NOT EXISTS user_id        uuid,
  ADD COLUMN IF NOT EXISTS amount_paise   bigint,
  ADD COLUMN IF NOT EXISTS failure_reason text,
  ADD COLUMN IF NOT EXISTS failure_code   text,
  ADD COLUMN IF NOT EXISTS updated_at     timestamptz NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_payments_order_id      ON public.payments(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_status_created  ON public.orders(status, created_at);

-- ── 2. Auto-touch updated_at triggers (same pattern already used on carts) ─
CREATE OR REPLACE FUNCTION public.fn_touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_orders_touch_updated_at ON public.orders;
CREATE TRIGGER trg_orders_touch_updated_at
  BEFORE UPDATE ON public.orders
  FOR EACH ROW EXECUTE FUNCTION public.fn_touch_updated_at();

DROP TRIGGER IF EXISTS trg_payments_touch_updated_at ON public.payments;
CREATE TRIGGER trg_payments_touch_updated_at
  BEFORE UPDATE ON public.payments
  FOR EACH ROW EXECUTE FUNCTION public.fn_touch_updated_at();

-- ── 3. Webhook idempotency ledger ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.stripe_webhook_events (
  event_id           text PRIMARY KEY,
  event_type         text NOT NULL,
  payment_intent_id  text,
  received_at        timestamptz NOT NULL DEFAULT now()
);

-- ── 4. settle_order_transaction (FIXED) ──────────────────────────────────
CREATE OR REPLACE FUNCTION public.settle_order_transaction(
    p_order_id uuid,
    p_pi_id    text,
    p_amount   numeric,
    p_user_id  uuid
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_status text;
BEGIN
    SELECT status
      INTO v_current_status
      FROM public.orders
     WHERE id          = p_order_id
       AND customer_id = p_user_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found for user %', p_order_id, p_user_id;
    END IF;

    -- Idempotency guard: already settled (webhook retry / confirm+webhook race)
    IF v_current_status = 'paid' THEN
        RETURN 'ALREADY_PAID';
    END IF;

    -- 🔒 Terminal-state guard: never resurrect a cancelled/refunded order.
    -- Its stock has already been released back to the pool (and may have
    -- been sold to someone else) -- flipping it to 'paid' here would create
    -- an unfulfillable paid order and a phantom stock deficit. Record the
    -- payment as an orphaned success instead; the caller is responsible for
    -- issuing a refund and alerting an operator.
    IF v_current_status IN ('cancelled', 'refunded') THEN
        UPDATE public.payments
           SET status = 'succeeded_orphaned',
               amount = p_amount,
               amount_paise = ROUND(p_amount * 100)
         WHERE stripe_payment_intent_id = p_pi_id;

        RETURN 'ORDER_ALREADY_CANCELLED';
    END IF;

    UPDATE public.orders
       SET status                = 'paid',
           stripe_payment_intent  = p_pi_id
     WHERE id = p_order_id;

    -- Record payment. ON CONFLICT DO UPDATE (not DO NOTHING) so the row we
    -- eagerly created at intent-creation time ('requires_payment_method')
    -- correctly transitions to 'succeeded' here.
    INSERT INTO public.payments (
        order_id, user_id, stripe_payment_intent_id, amount, amount_paise,
        currency, status, payment_method
    ) VALUES (
        p_order_id, p_user_id, p_pi_id, p_amount, ROUND(p_amount * 100),
        'INR', 'succeeded', 'card'
    )
    ON CONFLICT (stripe_payment_intent_id) DO UPDATE
        SET status       = 'succeeded',
            amount        = EXCLUDED.amount,
            amount_paise  = EXCLUDED.amount_paise,
            order_id      = EXCLUDED.order_id,
            user_id       = EXCLUDED.user_id;

    RETURN 'SETTLED';
END;
$$;

-- ── 5. cancel_order_and_release_stock (MERGED Gemini + Sentry) ───────────
CREATE OR REPLACE FUNCTION public.cancel_order_and_release_stock(
    p_order_id uuid,
    p_reason   text DEFAULT 'order_cancelled'
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_current_status text;
    v_item           record;
    v_stock_after    integer;
BEGIN
    -- Row lock: prevent concurrent modifications (webhook + cron racing)
    SELECT status
      INTO v_current_status
      FROM public.orders
     WHERE id = p_order_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % not found', p_order_id;
    END IF;

    -- Idempotency guard: already cancelled -- stock was already restored,
    -- never restore it twice.
    IF v_current_status = 'cancelled' THEN
        RETURN 'ALREADY_CANCELLED';
    END IF;

    -- Terminal-state guard: never cancel an order that has already shipped.
    IF v_current_status IN ('shipped', 'delivered', 'refunded') THEN
        RAISE EXCEPTION 'Cannot cancel order % in terminal status %', p_order_id, v_current_status;
    END IF;

    -- Mark order cancelled (Gemini: timestamps + human-readable note)
    UPDATE public.orders
       SET status       = 'cancelled',
           cancelled_at = now(),
           notes        = COALESCE(notes || E'\n', '')
                            || format('[%s] Cancelled: %s', now(), p_reason)
     WHERE id = p_order_id;

    -- Restore stock for each item + write audit rows (Sentry)
    -- Product row is locked too, so two orders cancelling for the same SKU
    -- at the same instant can't lose an update to each other.
    FOR v_item IN
        SELECT oi.product_id, oi.quantity, p.sku, p.stock
          FROM public.order_items oi
          JOIN public.products p ON p.id = oi.product_id
         WHERE oi.order_id = p_order_id
         FOR UPDATE OF p
    LOOP
        v_stock_after := v_item.stock + v_item.quantity;

        UPDATE public.products
           SET stock = v_stock_after
         WHERE id = v_item.product_id;

        INSERT INTO public.stock_audit (product_id, sku, delta, stock_after, reason)
        VALUES (
            v_item.product_id,
            v_item.sku,
            v_item.quantity,       -- positive delta = stock restored
            v_stock_after,
            'order_cancelled:' || p_order_id::text || ':' || p_reason
        );
    END LOOP;

    -- Close out any payments rows for this order that aren't already a
    -- terminal success/refund -- so the payments table always reflects
    -- reality (no row left dangling at 'requires_payment_method'/'failed'
    -- forever on a dead order).
    UPDATE public.payments
       SET status = 'cancelled'
     WHERE order_id = p_order_id
       AND status NOT IN ('succeeded', 'refunded', 'succeeded_orphaned');

    RETURN 'CANCELLED';
END;
$$;

-- ── 6. mark_payment_failed (NEW) ─────────────────────────────────────────
-- Records a failed PaymentIntent attempt. Insert-if-missing, update-if-
-- present -- but NEVER downgrades a row that's already succeeded/refunded,
-- which protects against Stripe delivering a stale 'payment_failed' event
-- out of order, after a 'succeeded' event for a later retry has already
-- landed.
CREATE OR REPLACE FUNCTION public.mark_payment_failed(
    p_order_id   uuid,
    p_user_id    uuid,
    p_pi_id      text,
    p_amount     numeric,
    p_reason     text DEFAULT NULL,
    p_error_code text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    INSERT INTO public.payments (
        order_id, user_id, stripe_payment_intent_id, amount, amount_paise,
        currency, status, failure_reason, failure_code
    ) VALUES (
        p_order_id, p_user_id, p_pi_id, p_amount, ROUND(p_amount * 100),
        'INR', 'failed', p_reason, p_error_code
    )
    ON CONFLICT (stripe_payment_intent_id) DO UPDATE
        SET status         = 'failed',
            failure_reason = EXCLUDED.failure_reason,
            failure_code   = EXCLUDED.failure_code
        WHERE public.payments.status NOT IN ('succeeded', 'refunded', 'succeeded_orphaned');
END;
$$;