-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.addresses (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid,
  line1 text NOT NULL,
  line2 text,
  city text NOT NULL,
  state text,
  postal_code text NOT NULL,
  country character NOT NULL,
  is_default boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT addresses_pkey PRIMARY KEY (id),
  CONSTRAINT addresses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.categories (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  description text,
  image_url text,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT categories_pkey PRIMARY KEY (id)
);
CREATE TABLE public.order_items (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  order_id uuid,
  product_id uuid,
  product_name text,
  unit_price numeric NOT NULL,
  quantity integer NOT NULL,
  subtotal numeric,
  CONSTRAINT order_items_pkey PRIMARY KEY (id),
  CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id),
  CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.orders (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  customer_id uuid,
  status text DEFAULT 'pending'::text,
  subtotal numeric,
  shipping_cost numeric,
  tax_amount numeric,
  total_amount numeric,
  currency text DEFAULT 'INR',
  stripe_payment_intent text,
  shipping_line1 text,
  shipping_line2 text,
  shipping_city text,
  shipping_state text,
  shipping_postal_code text,
  shipping_country text,
  notes text,
  tracking_number text,
  created_at timestamp with time zone DEFAULT now(),
  shipping_address_id uuid,
  CONSTRAINT orders_pkey PRIMARY KEY (id),
  CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.users(id),
  CONSTRAINT orders_shipping_address_id_fkey FOREIGN KEY (shipping_address_id) REFERENCES public.addresses(id)
);
CREATE TABLE public.payments (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  order_id uuid,
  stripe_payment_intent_id text UNIQUE,
  amount numeric,
  currency text,
  status text,
  payment_method text,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT payments_pkey PRIMARY KEY (id),
  CONSTRAINT payments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id)
);
CREATE TABLE public.product_images (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  product_id uuid,
  url text NOT NULL,
  alt text,
  position integer DEFAULT 0,
  CONSTRAINT product_images_pkey PRIMARY KEY (id),
  CONSTRAINT product_images_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.products (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  description text,
  short_description text,
  sku text,
  category_id uuid,
  price numeric NOT NULL,
  compare_price numeric,
  stock integer DEFAULT 0,
  low_stock_threshold integer DEFAULT 10,
  weight_grams integer,
  image_url text,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  fts tsvector DEFAULT to_tsvector('english'::regconfig, COALESCE(name, ''::text)),
  CONSTRAINT products_pkey PRIMARY KEY (id),
  CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id)
);
CREATE TABLE public.push_subscriptions (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  endpoint text NOT NULL UNIQUE,
  subscription_json text NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id),
  CONSTRAINT push_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.stock_audit (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  product_id uuid NOT NULL,
  sku text,
  delta integer NOT NULL,
  stock_after integer,
  reason text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT stock_audit_pkey PRIMARY KEY (id),
  CONSTRAINT stock_audit_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.users (
  id uuid NOT NULL,
  email text NOT NULL,
  full_name text DEFAULT ''::text,
  phone text DEFAULT ''::text,
  role text DEFAULT 'customer'::text CHECK (role = ANY (ARRAY['customer'::text, 'admin'::text])),
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT users_pkey PRIMARY KEY (id),
  CONSTRAINT users_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id)
);





-- ═══════════════════════════════════════════════════════════════════════════
--  Cart + Pricing Migration
--  Run once in Supabase Dashboard → SQL Editor
--  Tables: carts, cart_items
--  Trigger: auto-update carts.updated_at on item change
--  Indexes: user_id, updated_at, cart_id
-- ═══════════════════════════════════════════════════════════════════════════

-- ── 1. carts — one row per user ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.carts (
  id         uuid        NOT NULL DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT carts_pkey         PRIMARY KEY (id),
  CONSTRAINT carts_user_id_uq   UNIQUE (user_id),           -- one cart per user
  CONSTRAINT carts_user_id_fkey FOREIGN KEY (user_id)
    REFERENCES public.users(id) ON DELETE CASCADE
);

-- ── 2. cart_items — line items inside a cart ──────────────────────────────────
CREATE TABLE IF NOT EXISTS public.cart_items (
  id             uuid        NOT NULL DEFAULT gen_random_uuid(),
  cart_id        uuid        NOT NULL,
  product_id     uuid        NOT NULL,
  quantity       integer     NOT NULL CHECK (quantity > 0 AND quantity <= 100),
  -- Price at time of adding — guards against price changes between add and checkout.
  -- Frontend displays this; checkout uses live product.price for actual billing.
  price_snapshot numeric     NOT NULL,
  added_at       timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT cart_items_pkey           PRIMARY KEY (id),
  CONSTRAINT cart_items_cart_product_uq UNIQUE (cart_id, product_id),   -- no duplicates
  CONSTRAINT cart_items_cart_id_fkey   FOREIGN KEY (cart_id)
    REFERENCES public.carts(id) ON DELETE CASCADE,
  CONSTRAINT cart_items_product_id_fkey FOREIGN KEY (product_id)
    REFERENCES public.products(id)
);

-- ── 3. Trigger — auto-bump carts.updated_at on any item change ────────────────
--  WHY: Abandoned cart detection relies on updated_at.
--  Without this, adding/removing items would not update the cart timestamp.
CREATE OR REPLACE FUNCTION public.fn_cart_items_touch_cart()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE public.carts
  SET    updated_at = now()
  WHERE  id = COALESCE(NEW.cart_id, OLD.cart_id);
  RETURN NULL;  -- AFTER trigger, return value ignored
END;
$$;

DROP TRIGGER IF EXISTS trg_cart_items_touch ON public.cart_items;
CREATE TRIGGER trg_cart_items_touch
  AFTER INSERT OR UPDATE OR DELETE ON public.cart_items
  FOR EACH ROW EXECUTE FUNCTION public.fn_cart_items_touch_cart();

-- ── 4. Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_carts_user_id    ON public.carts(user_id);
-- Used by admin abandoned-cart query: WHERE updated_at < now() - interval AND has items
CREATE INDEX IF NOT EXISTS idx_carts_updated_at ON public.carts(updated_at);
CREATE INDEX IF NOT EXISTS idx_cart_items_cart  ON public.cart_items(cart_id);

-- ── 5. RLS — service role bypasses; anon/customer cannot read other carts ─────
ALTER TABLE public.carts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cart_items ENABLE ROW LEVEL SECURITY;

-- Service role (used by backend) bypasses RLS automatically.
-- These policies allow authenticated users to read/write ONLY their own cart.
-- If you use the anon key on the frontend directly, add these policies.
-- Backend uses service role key → these policies are informational / best-practice.

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='carts' AND policyname='carts_owner'
  ) THEN
    CREATE POLICY carts_owner ON public.carts
      FOR ALL USING (user_id = auth.uid());
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename='cart_items' AND policyname='cart_items_owner'
  ) THEN
    CREATE POLICY cart_items_owner ON public.cart_items
      FOR ALL USING (
        cart_id IN (SELECT id FROM public.carts WHERE user_id = auth.uid())
      );
  END IF;
END $$;