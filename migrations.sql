-- =============================================================================
-- MyStore — Complete Database Migrations
-- Generated from codebase scan
--
-- Supabase SQL Editor mein run karo (ek baar)
-- Safe to re-run — sab IF NOT EXISTS use karta hai
-- =============================================================================


-- =============================================================================
-- SECTION 1: TABLE SCHEMAS
-- =============================================================================

-- Users (Supabase Auth ke saath sync)
CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email       text NOT NULL,
    full_name   text,
    phone       text,
    role        text NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin')),
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    slug        text NOT NULL,
    description text,
    image_url   text,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL,
    slug                text NOT NULL,
    description         text,
    short_description   text,
    sku                 text,
    category_id         uuid REFERENCES categories(id) ON DELETE SET NULL,
    price               numeric(10,2) NOT NULL CHECK (price > 0),
    compare_price       numeric(10,2) CHECK (compare_price > 0),
    stock               int NOT NULL DEFAULT 0 CHECK (stock >= 0),
    low_stock_threshold int NOT NULL DEFAULT 10,
    weight_grams        int CHECK (weight_grams >= 0),
    image_url           text,
    is_active           boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now()
);

-- Product images (multiple images per product)
CREATE TABLE IF NOT EXISTS product_images (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id  uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    url         text NOT NULL,
    position    int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Addresses
CREATE TABLE IF NOT EXISTS addresses (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    line1       text NOT NULL,
    line2       text,
    city        text NOT NULL,
    state       text,
    postal_code text NOT NULL,
    country     char(2) NOT NULL,
    is_default  boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id          uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    shipping_address_id  uuid REFERENCES addresses(id) ON DELETE SET NULL,
    status               text NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending','paid','shipped','delivered','cancelled','refunded')),
    subtotal             numeric(10,2) NOT NULL,
    shipping_cost        numeric(10,2) NOT NULL DEFAULT 0,
    tax_amount           numeric(10,2) NOT NULL DEFAULT 0,
    total_amount         numeric(10,2) NOT NULL,
    shipping_line1       text,
    shipping_line2       text,
    shipping_city        text,
    shipping_state       text,
    shipping_postal_code text,
    shipping_country     char(2),
    notes                text,
    stripe_payment_intent text,
    tracking_number      text,
    currency             char(3) NOT NULL DEFAULT 'usd',
    created_at           timestamptz NOT NULL DEFAULT now()
);

-- Order items
CREATE TABLE IF NOT EXISTS order_items (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id     uuid NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id   uuid REFERENCES products(id) ON DELETE SET NULL,
    product_name text NOT NULL,
    unit_price   numeric(10,2) NOT NULL,
    quantity     int NOT NULL CHECK (quantity > 0),
    subtotal     numeric(10,2) NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Payments
CREATE TABLE IF NOT EXISTS payments (
    id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id                 uuid NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    stripe_payment_intent_id text NOT NULL,
    amount                   numeric(10,2) NOT NULL,
    currency                 char(3) NOT NULL DEFAULT 'USD',
    status                   text NOT NULL DEFAULT 'completed',
    payment_method           text NOT NULL DEFAULT 'stripe',
    created_at               timestamptz NOT NULL DEFAULT now()
);


-- =============================================================================
-- SECTION 2: UNIQUE CONSTRAINTS
-- =============================================================================

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'products_slug_unique') THEN
    ALTER TABLE products ADD CONSTRAINT products_slug_unique UNIQUE (slug);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'categories_slug_unique') THEN
    ALTER TABLE categories ADD CONSTRAINT categories_slug_unique UNIQUE (slug);
  END IF;
END $$;

-- SKU unique — nullable (NULL values allowed)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'products_sku_unique_idx') THEN
    CREATE UNIQUE INDEX products_sku_unique_idx ON products(sku) WHERE sku IS NOT NULL;
  END IF;
END $$;

-- Payments — webhook replay protection
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'payments_pi_unique') THEN
    ALTER TABLE payments ADD CONSTRAINT payments_pi_unique UNIQUE (stripe_payment_intent_id);
  END IF;
END $$;


-- =============================================================================
-- SECTION 3: RPC FUNCTIONS
-- =============================================================================

-- Atomic stock restore — cancel / payment failed / rollback
-- Usage: sb.rpc("increment_stock", {"p_id": "uuid", "p_qty": 5}).execute()
CREATE OR REPLACE FUNCTION increment_stock(p_id uuid, p_qty int)
RETURNS void LANGUAGE sql AS $$
  UPDATE products SET stock = stock + p_qty WHERE id = p_id;
$$;

-- Atomic stock deduct — order create
-- Returns remaining stock row; empty result = insufficient stock
-- Usage: sb.rpc("decrement_stock", {"p_id": "uuid", "p_qty": 5}).execute()
CREATE OR REPLACE FUNCTION decrement_stock(p_id uuid, p_qty int)
RETURNS int LANGUAGE sql AS $$
  UPDATE products
  SET stock = stock - p_qty
  WHERE id = p_id AND stock >= p_qty
  RETURNING stock;
$$;


-- =============================================================================
-- SECTION 4: FULL-TEXT SEARCH
-- =============================================================================

ALTER TABLE products
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english',
      coalesce(name, '') || ' ' || coalesce(description, '') || ' ' || coalesce(short_description, '')
    )
  ) STORED;

CREATE INDEX IF NOT EXISTS products_fts_idx ON products USING GIN(fts);


-- =============================================================================
-- SECTION 5: PERFORMANCE INDEXES
-- =============================================================================

CREATE INDEX IF NOT EXISTS orders_customer_id_idx    ON orders(customer_id);
CREATE INDEX IF NOT EXISTS orders_status_idx         ON orders(status);
CREATE INDEX IF NOT EXISTS orders_created_at_idx     ON orders(created_at DESC);
CREATE INDEX IF NOT EXISTS orders_stripe_pi_idx      ON orders(stripe_payment_intent) WHERE stripe_payment_intent IS NOT NULL;
CREATE INDEX IF NOT EXISTS order_items_order_id_idx  ON order_items(order_id);
CREATE INDEX IF NOT EXISTS order_items_product_id_idx ON order_items(product_id);
CREATE INDEX IF NOT EXISTS addresses_user_id_idx     ON addresses(user_id);
CREATE INDEX IF NOT EXISTS products_category_id_idx  ON products(category_id) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS products_is_active_idx    ON products(is_active);
CREATE INDEX IF NOT EXISTS products_price_idx        ON products(price) WHERE is_active = true;


-- =============================================================================
-- SECTION 6: AUTH TRIGGER
-- Register hone pe auth.users → public.users sync
-- =============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name, role, is_active)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
    'customer',
    true
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- =============================================================================
-- SECTION 7: ROW LEVEL SECURITY (optional — recommended for production)
-- Service role key (backend) automatically bypasses RLS
-- =============================================================================

ALTER TABLE users        ENABLE ROW LEVEL SECURITY;
ALTER TABLE addresses    ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders       ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items  ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments     ENABLE ROW LEVEL SECURITY;

-- Products aur categories public hain — koi RLS nahi

-- Users: apna profile sirf khud dekh sakta hai
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_profile') THEN
    CREATE POLICY users_own_profile ON users FOR ALL USING (auth.uid() = id);
  END IF;
END $$;

-- Addresses: apne addresses sirf khud
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'addresses_own') THEN
    CREATE POLICY addresses_own ON addresses FOR ALL USING (auth.uid() = user_id);
  END IF;
END $$;

-- Orders: apne orders sirf khud
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'orders_own') THEN
    CREATE POLICY orders_own ON orders FOR SELECT USING (auth.uid() = customer_id);
  END IF;
END $$;

-- Order items: apne order items sirf khud
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'order_items_own') THEN
    CREATE POLICY order_items_own ON order_items FOR SELECT
    USING (order_id IN (SELECT id FROM orders WHERE customer_id = auth.uid()));
  END IF;
END $$;


-- =============================================================================
-- COMPLETED
-- Dashboard mein manually karo:
-- 1. Settings → JWT Keys → Access token expiry → 900 (15 min)
-- 2. Auth → Sessions → Refresh Token Rotation → ON
-- 3. Storage → product-images → Public → ON
-- =============================================================================