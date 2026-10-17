-- Repair subscription schema drift and provision the existing Free plan for customers.
-- Safe to re-run: additive DDL, idempotent backfill, trigger replacement.

ALTER TABLE public.user_subscriptions
    ADD COLUMN IF NOT EXISTS cancelled_at timestamptz,
    ADD COLUMN IF NOT EXISTS cancellation_reason text;

CREATE TABLE IF NOT EXISTS public.subscription_reminders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id uuid NOT NULL REFERENCES public.user_subscriptions(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    reminder_type text NOT NULL CHECK (reminder_type IN ('7d', '1d', 'expired')),
    due_at timestamptz NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'sent', 'dismissed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    dismissed_at timestamptz,
    CONSTRAINT uq_subscription_reminders_subscription_type
        UNIQUE (subscription_id, reminder_type)
);

CREATE INDEX IF NOT EXISTS idx_subscription_reminders_user_status
    ON public.subscription_reminders (user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_reminders_due_status
    ON public.subscription_reminders (due_at, status);

ALTER TABLE public.subscription_reminders ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS subscription_reminders_select_own ON public.subscription_reminders;
CREATE POLICY subscription_reminders_select_own
    ON public.subscription_reminders
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS subscription_reminders_update_own ON public.subscription_reminders;
CREATE POLICY subscription_reminders_update_own
    ON public.subscription_reminders
    FOR UPDATE TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

-- Preserve the current Free plan catalogue values if it already exists.
INSERT INTO public.subscription_plans (tier, name, price_inr, duration_days, description, is_active)
SELECT 'free', 'Free', 0, 30, 'Basic shopping. Standard shipping rates, no member discount.', true
WHERE NOT EXISTS (
    SELECT 1 FROM public.subscription_plans
    WHERE tier = 'free' AND is_active = true
);

-- Staff accounts must never carry a customer membership. Keep history instead of deleting it.
UPDATE public.user_subscriptions AS s
SET status = 'cancelled',
    cancelled_at = COALESCE(s.cancelled_at, now()),
    cancellation_reason = COALESCE(
        NULLIF(btrim(s.cancellation_reason), ''),
        'Staff accounts do not receive customer memberships.'
    ),
    updated_at = now()
FROM public.users AS u
WHERE u.id = s.user_id
  AND u.role <> 'customer'
  AND s.tier = 'free'
  AND s.status = 'active'
  AND (s.ends_at IS NULL OR s.ends_at > now());

-- Backfill existing customer accounts missing an active subscription.
-- Use the active Free plan ID and its configured duration; never overwrite a valid paid plan.
WITH free_plan AS (
    SELECT id, name, GREATEST(duration_days, 1) AS duration_days
    FROM public.subscription_plans
    WHERE tier = 'free' AND is_active = true
    ORDER BY price_inr ASC, created_at ASC
    LIMIT 1
)
INSERT INTO public.user_subscriptions
    (user_id, plan_id, plan_name, tier, status, starts_at, ends_at)
SELECT u.id, fp.id, fp.name, 'free', 'active', now(),
       now() + make_interval(days => fp.duration_days)
FROM public.users AS u
CROSS JOIN free_plan AS fp
WHERE u.role = 'customer'
  AND NOT EXISTS (
      SELECT 1
      FROM public.user_subscriptions AS s
      WHERE s.user_id = u.id
        AND s.status = 'active'
        AND (s.ends_at IS NULL OR s.ends_at > now())
  );

-- Registration profile creation is the authoritative point at which the
-- customer receives the Free membership. The trigger and backfill share the
-- same plan lookup and duration semantics.
CREATE OR REPLACE FUNCTION public.provision_default_free_subscription()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_plan public.subscription_plans%ROWTYPE;
BEGIN
    IF NEW.role IS DISTINCT FROM 'customer' THEN
        RETURN NEW;
    END IF;

    SELECT *
    INTO v_plan
    FROM public.subscription_plans
    WHERE tier = 'free' AND is_active = true
    ORDER BY price_inr ASC, created_at ASC
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cannot provision default customer subscription: active Free plan is missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.user_subscriptions AS s
        WHERE s.user_id = NEW.id
          AND s.status = 'active'
          AND (s.ends_at IS NULL OR s.ends_at > now())
    ) THEN
        INSERT INTO public.user_subscriptions
            (user_id, plan_id, plan_name, tier, status, starts_at, ends_at)
        VALUES (
            NEW.id, v_plan.id, v_plan.name, 'free', 'active', now(),
            now() + make_interval(days => GREATEST(v_plan.duration_days, 1))
        );
    END IF;

    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.provision_default_free_subscription() FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS users_provision_default_free_subscription ON public.users;
CREATE TRIGGER users_provision_default_free_subscription
AFTER INSERT ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.provision_default_free_subscription();

NOTIFY pgrst, 'reload schema';
