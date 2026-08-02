-- ═══════════════════════════════════════════════════════════════════════════
-- Migration 006: ip_address type fix + webhook idempotency correctness fix
-- ═══════════════════════════════════════════════════════════════════════════
-- Bug 1: `payments.ip_address` already existed in production as `inet`
-- (from before this migration series -- not present in the repo's tracked
-- migrations). Migration 005's `ADD COLUMN IF NOT EXISTS ip_address text`
-- was a no-op against that existing column, so it stayed `inet`, and the
-- app's plain string writes started failing with:
--   "column ip_address is of type inet but expression is of type text"
-- Fixed by converting it to `text` -- this is a log/audit field (can hold
-- comma-separated X-Forwarded-For values, "unknown", IPv6, etc.), `inet`
-- was too strict for it anyway.
--
-- Bug 2 (found via the crash above): `stripe_webhook_events` marked an
-- event as "seen" the INSTANT it was received, before processing even
-- started. So when processing then failed (for any reason -- the bug
-- above, a transient DB blip, anything), we returned 500 to Stripe, Stripe
-- retried as designed -- and our own ledger told us "already handled,
-- skip" and we answered 200. Stripe stops retrying after a 200. Net
-- result: a real successful payment can get stuck in 'pending' forever
-- with no further signal from Stripe. Fixed by only marking an event
-- "processed" AFTER its handler completes without error; a delivery for
-- an event that was received but never finished processing is now
-- correctly treated as "not yet done" and reprocessed (safe -- every RPC
-- in this flow is already idempotent: ALREADY_PAID / ALREADY_CANCELLED
-- guards mean reprocessing can't double-charge or double-cancel).
-- Safe to run multiple times.
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. Fix ip_address column type ────────────────────────────────────────
ALTER TABLE public.payments
  ALTER COLUMN ip_address TYPE text USING ip_address::text;

-- Defensive -- in case user_agent was also something other than text.
ALTER TABLE public.payments
  ALTER COLUMN user_agent TYPE text USING user_agent::text;

-- ── 2. Webhook idempotency: mark-processed-AFTER-success, not before ────
ALTER TABLE public.stripe_webhook_events
  ADD COLUMN IF NOT EXISTS processed_at timestamptz;

-- Atomically claims an event: inserts it if new, and tells the caller
-- whether they should process it now. Returns TRUE when:
--   * this is a brand-new event_id, OR
--   * it was received before but never successfully finished processing
--     (processed_at IS NULL) -- e.g. the previous attempt crashed.
-- Returns FALSE only when the event was already fully processed --
-- a genuine duplicate delivery that's safe to skip.
CREATE OR REPLACE FUNCTION public.claim_webhook_event(
    p_event_id   text,
    p_event_type text,
    p_pi_id      text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_processed_at timestamptz;
BEGIN
    INSERT INTO public.stripe_webhook_events (event_id, event_type, payment_intent_id)
    VALUES (p_event_id, p_event_type, p_pi_id)
    ON CONFLICT (event_id) DO NOTHING;

    SELECT processed_at INTO v_processed_at
      FROM public.stripe_webhook_events
     WHERE event_id = p_event_id;

    RETURN v_processed_at IS NULL;
END;
$$;

CREATE OR REPLACE FUNCTION public.mark_webhook_event_processed(p_event_id text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
    UPDATE public.stripe_webhook_events
       SET processed_at = now()
     WHERE event_id = p_event_id;
$$;