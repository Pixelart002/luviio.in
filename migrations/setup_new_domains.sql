-- ═══════════════════════════════════════════════════════════════════════════════
--  LUVIIO — NEW DOMAINS SCHEMA SETUP (RBAC / COUPONS / SHIPPING / SUBSCRIPTIONS)
--  Path: migrations/setup_new_domains.sql
--
--  🔴 RUN THIS ONCE in Supabase SQL Editor (or via `supabase db push`).
--  Idempotent-ish: uses `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ... ADD COLUMN
--  IF NOT EXISTS`, so re-running is safe.
--
--  Creates:
--    * users.tier                  (free | premium | platinum) — added to `users`
--    * role_permissions            role-level permission toggles (RBAC)
--    * user_action_controls        per-user action disable (big-software pattern)
--    * coupons + coupon_redemptions + consume_coupon() RPC
--    * shipping_methods
--    * subscription_plans + user_subscriptions
-- ═══════════════════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────────────────
-- 0. users.tier (legacy tier column consumed by pricing)
-- ──────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS tier TEXT DEFAULT 'free';
UPDATE public.users SET tier = 'free' WHERE tier IS NULL;
COMMENT ON COLUMN public.users.tier IS 'Effective subscription tier: free | premium | platinum (subscriptions domain SSOT).';

-- ──────────────────────────────────────────────────────────────────────────────
-- 1. RBAC — role-level permission overrides
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.role_permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role        TEXT NOT NULL,                 -- e.g. 'admin', 'manager', 'support', 'customer'
    permission  TEXT NOT NULL,                 -- e.g. 'admin.manage_roles', 'coupons.create'
    enabled     BOOLEAN NOT NULL DEFAULT TRUE, -- TRUE adds to static base, FALSE revokes it
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (role, permission)
);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON public.role_permissions (role);

-- ──────────────────────────────────────────────────────────────────────────────
-- 2. RBAC — per-user action controls (disable checkout/apply_coupon/etc per user)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_action_controls (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    action      TEXT NOT NULL,                 -- e.g. 'checkout', 'apply_coupon', 'place_order'
    enabled     BOOLEAN NOT NULL DEFAULT TRUE, -- FALSE = action blocked for this user
    reason      TEXT NOT NULL DEFAULT '',
    updated_by  UUID,                          -- admin (actor) who changed it
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, action)
);
CREATE INDEX IF NOT EXISTS idx_user_action_controls_user ON public.user_action_controls (user_id);

-- ──────────────────────────────────────────────────────────────────────────────
-- 3. Coupons
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.coupons (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code             TEXT NOT NULL UNIQUE,     -- uppercase alias, e.g. 'SAVE10'
    type             TEXT NOT NULL DEFAULT 'percent' CHECK (type IN ('percent', 'fixed')),
    value            NUMERIC(12,2) NOT NULL,   -- percent (0-100) or fixed INR amount
    min_order_amount NUMERIC(12,2) DEFAULT 0,
    max_discount     NUMERIC(12,2),            -- cap for percent coupons
    valid_from       TIMESTAMPTZ,
    valid_until      TIMESTAMPTZ,
    usage_limit      INTEGER,                  -- NULL = unlimited
    per_user_limit   INTEGER DEFAULT 1,
    used_count       INTEGER NOT NULL DEFAULT 0,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coupons_code ON public.coupons (code);
CREATE INDEX IF NOT EXISTS idx_coupons_active ON public.coupons (is_active);

-- ──────────────────────────────────────────────────────────────────────────────
-- 4. Coupon redemptions + atomic consume RPC
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.coupon_redemptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id   UUID NOT NULL REFERENCES public.coupons(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,
    order_id    UUID,
    discount    NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cpn_red_coupon ON public.coupon_redemptions (coupon_id);
CREATE INDEX IF NOT EXISTS idx_cpn_red_user   ON public.coupon_redemptions (coupon_id, user_id);
-- Hard idempotency guard: a coupon can only ever be redeemed once per order
-- (partial because order_id is nullable for non-checkout rows).
CREATE UNIQUE INDEX IF NOT EXISTS uq_cpn_red_order
    ON public.coupon_redemptions (coupon_id, order_id)
    WHERE order_id IS NOT NULL;

-- consume_coupon: atomically increments used_count in a transaction.
-- If the coupon hits usage_limit, it throws so the redemption cannot record.
CREATE OR REPLACE FUNCTION public.consume_coupon(p_coupon_id UUID, p_user_id UUID, p_order_id UUID)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_limit INTEGER;
    v_used  INTEGER;
BEGIN
    SELECT usage_limit, used_count INTO v_limit, v_used
    FROM public.coupons WHERE id = p_coupon_id FOR UPDATE;

    IF v_limit IS NOT NULL AND v_used >= v_limit THEN
        RAISE EXCEPTION 'Coupon usage limit reached';
    END IF;

    UPDATE public.coupons
    SET used_count = used_count + 1, updated_at = now()
    WHERE id = p_coupon_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- 5. Shipping methods
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.shipping_methods (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name           TEXT NOT NULL,
    type           TEXT NOT NULL DEFAULT 'flat'
                   CHECK (type IN ('flat', 'free_threshold', 'per_item', 'weight')),
    base_rate      NUMERIC(12,2) NOT NULL DEFAULT 0,
    threshold      NUMERIC(12,2),              -- free-above threshold (free_threshold)
    per_item_rate  NUMERIC(12,2),              -- per-unit add-on (per_item)
    weight_rate    NUMERIC(12,2),              -- per-kg rate (weight)
    estimated_days INTEGER NOT NULL DEFAULT 3,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order     INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shipping_active ON public.shipping_methods (is_active, sort_order);

-- ──────────────────────────────────────────────────────────────────────────────
-- 6. Subscription plans (catalogue of per-tier price; NOT product price)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.subscription_plans (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier          TEXT NOT NULL CHECK (tier IN ('free', 'premium', 'platinum')),
    name          TEXT NOT NULL,
    price_inr     NUMERIC(12,2) NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 30,
    description   TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sub_plans_tier ON public.subscription_plans (tier, is_active);

-- Seed the standard 3 tiers (idempotent: skip existing names).
INSERT INTO public.subscription_plans (tier, name, price_inr, duration_days, description)
SELECT * FROM (VALUES
    ('free',    'Free',      0.00,   30, 'Basic shopping. Standard shipping rates, no member discount.'),
    ('premium', 'Premium',   199.00, 30, 'Free shipping + 5% member discount on orders.'),
    ('platinum','Platinum',  499.00, 30, 'Free shipping + 10% member discount, premium & platinum product access.')
) AS seed(tier, name, price_inr, duration_days, description)
WHERE NOT EXISTS (SELECT 1 FROM public.subscription_plans sp WHERE sp.tier = seed.tier);

-- ──────────────────────────────────────────────────────────────────────────────
-- 7. User subscriptions (active grant of a tier to a user)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.user_subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,
    plan_id     UUID REFERENCES public.subscription_plans(id) ON DELETE SET NULL,
    plan_name   TEXT,
    tier        TEXT NOT NULL DEFAULT 'free',
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'expired')),
    starts_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ends_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_subs_active
    ON public.user_subscriptions (user_id, status, ends_at DESC);

-- ──────────────────────────────────────────────────────────────────────────────
-- 7b. Orders — coupon columns (the orders table already exists; add idempotently)
--      These back the coupon discount recorded at checkout + on payment.
-- ──────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.orders
    ADD COLUMN IF NOT EXISTS coupon_id     UUID,
    ADD COLUMN IF NOT EXISTS coupon_code   TEXT,
    ADD COLUMN IF NOT EXISTS discount_amount NUMERIC(12,2) NOT NULL DEFAULT 0;
COMMENT ON COLUMN public.orders.coupon_id IS 'Applied coupon (coupons.id), resolved at checkout.';
COMMENT ON COLUMN public.orders.discount_amount IS 'Monetary discount applied via coupon (INR).';

-- ──────────────────────────────────────────────────────────────────────────────
-- 8. ROW LEVEL SECURITY
--    Admin service role bypasses RLS (service_role key). Public/app users read
--    only public catalogue rows; nothing user-editable except through the API.
-- ──────────────────────────────────────────────────────────────────────────────
ALTER TABLE public.role_permissions      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_action_controls  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupons               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupon_redemptions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shipping_methods      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscription_plans    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_subscriptions    ENABLE ROW LEVEL SECURITY;

-- Admin-only management tables: no anon/authenticated access; service role only.
CREATE POLICY "admin_write_role_permissions" ON public.role_permissions
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "admin_write_user_action_controls" ON public.user_action_controls
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "admin_write_coupons" ON public.coupons
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "admin_write_shipping_methods" ON public.shipping_methods
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');
CREATE POLICY "admin_write_subscription_plans" ON public.subscription_plans
    FOR ALL USING (auth.role() = 'service_role') WITH CHECK (auth.role() = 'service_role');

-- Subscription plans: public read (to render the pricing page).
CREATE POLICY "public_read_subscription_plans" ON public.subscription_plans
    FOR SELECT USING (true);

-- User subscriptions & coupon redemptions: user can only see their own rows.
CREATE POLICY "user_read_own_subscriptions" ON public.user_subscriptions
    FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "user_read_own_redemptions" ON public.coupon_redemptions
    FOR SELECT USING (auth.uid() = user_id);

-- ═══════════════════════════════════════════════════════════════════════════════
--  DONE — verify with:
--    SELECT table_name FROM information_schema.tables
--      WHERE table_schema='public' AND table_name IN
--      ('role_permissions','user_action_controls','coupons','coupon_redemptions',
--       'shipping_methods','subscription_plans','user_subscriptions');
-- ═══════════════════════════════════════════════════════════════════════════════
