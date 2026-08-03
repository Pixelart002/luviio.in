-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.users (
  updated_at timestamp with time zone DEFAULT now(),
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
CREATE TABLE public.categories (
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  description text,
  image_url text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  CONSTRAINT categories_pkey PRIMARY KEY (id)
);
CREATE TABLE public.products (
  hsn_code text DEFAULT '9988'::text,
  gst_percentage integer DEFAULT 18 CHECK (gst_percentage = ANY (ARRAY[0, 5, 12, 18, 28])),
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  description text,
  short_description text,
  sku text,
  category_id uuid,
  price numeric NOT NULL,
  compare_price numeric,
  weight_grams integer,
  image_url text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  stock integer DEFAULT 0,
  low_stock_threshold integer DEFAULT 10,
  is_active boolean DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  fts tsvector DEFAULT to_tsvector('english'::regconfig, COALESCE(name, ''::text)),
  discount_amount numeric DEFAULT 
CASE
    WHEN (compare_price > price) THEN round((compare_price - price), 2)
    ELSE 0.00
END,
  discount_percentage integer DEFAULT 
CASE
    WHEN (compare_price > price) THEN (round((((compare_price - price) / compare_price) * (100)::numeric)))::integer
    ELSE 0
END,
  images ARRAY DEFAULT '{}'::text[],
  CONSTRAINT products_pkey PRIMARY KEY (id),
  CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id)
);
CREATE TABLE public.product_images (
  product_id uuid,
  url text NOT NULL,
  alt text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  position integer DEFAULT 0,
  CONSTRAINT product_images_pkey PRIMARY KEY (id),
  CONSTRAINT product_images_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.addresses (
  user_id uuid,
  line1 text NOT NULL,
  line2 text,
  city text NOT NULL,
  state text,
  postal_code text NOT NULL,
  country character NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  is_default boolean DEFAULT false,
  created_at timestamp with time zone DEFAULT now(),
  deleted_at timestamp with time zone,
  full_name text,
  phone text,
  email text,
  landmark text,
  address_type text DEFAULT 'home'::text,
  company_name text,
  gstin text,
  CONSTRAINT addresses_pkey PRIMARY KEY (id),
  CONSTRAINT addresses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.orders (
  idempotency_key text UNIQUE,
  currency text DEFAULT 'INR'::text,
  updated_at timestamp with time zone DEFAULT now(),
  invoice_number text DEFAULT get_next_invoice_number(),
  tax_type text DEFAULT 'IGST'::text,
  order_number text UNIQUE,
  customer_id uuid,
  subtotal numeric,
  shipping_cost numeric,
  tax_amount numeric,
  total_amount numeric,
  stripe_payment_intent text,
  shipping_line1 text,
  shipping_line2 text,
  shipping_city text,
  shipping_state text,
  shipping_postal_code text,
  shipping_country text,
  notes text,
  tracking_number text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  status text DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'paid'::text, 'processing'::text, 'shipped'::text, 'delivered'::text, 'cancelled'::text, 'refunded'::text])),
  created_at timestamp with time zone DEFAULT now(),
  shipping_address_id uuid,
  shipping_name text,
  shipping_phone text,
  shipping_email text,
  shipping_landmark text,
  shipping_company_name text,
  shipping_gstin text,
  billing_same_as_shipping boolean DEFAULT true,
  billing_address_id uuid,
  billing_name text,
  billing_phone text,
  billing_email text,
  billing_line1 text,
  billing_line2 text,
  billing_landmark text,
  billing_city text,
  billing_state text,
  billing_postal_code text,
  billing_country text,
  billing_company_name text,
  billing_gstin text,
  fulfilled_at timestamp with time zone,
  cancelled_at timestamp with time zone,
  delivered_at timestamp with time zone,
  paid_at timestamp with time zone,
  shipped_at timestamp with time zone,
  refunded_at timestamp with time zone,
  CONSTRAINT orders_pkey PRIMARY KEY (id),
  CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.users(id),
  CONSTRAINT orders_shipping_address_id_fkey FOREIGN KEY (shipping_address_id) REFERENCES public.addresses(id)
);
CREATE TABLE public.order_items (
  compare_price numeric DEFAULT 0.00,
  hsn_code text DEFAULT '9988'::text,
  gst_percentage integer DEFAULT 18,
  tax_amount numeric DEFAULT 0.00,
  discount_amount numeric DEFAULT 0.00,
  order_id uuid,
  product_id uuid,
  product_name text,
  unit_price numeric NOT NULL,
  quantity integer NOT NULL,
  subtotal numeric,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  CONSTRAINT order_items_pkey PRIMARY KEY (id),
  CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id),
  CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.stock_audit (
  product_id uuid NOT NULL,
  sku text,
  delta integer NOT NULL,
  stock_after integer,
  reason text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT stock_audit_pkey PRIMARY KEY (id),
  CONSTRAINT stock_audit_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.push_subscriptions (
  user_id uuid NOT NULL,
  endpoint text NOT NULL UNIQUE,
  subscription_json text NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT push_subscriptions_pkey PRIMARY KEY (id),
  CONSTRAINT push_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.carts (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL UNIQUE,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT carts_pkey PRIMARY KEY (id),
  CONSTRAINT carts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.cart_items (
  cart_id uuid NOT NULL,
  product_id uuid NOT NULL,
  quantity integer NOT NULL CHECK (quantity > 0 AND quantity <= 100),
  price_snapshot numeric NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  added_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT cart_items_pkey PRIMARY KEY (id),
  CONSTRAINT cart_items_cart_id_fkey FOREIGN KEY (cart_id) REFERENCES public.carts(id),
  CONSTRAINT cart_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id)
);
CREATE TABLE public.pricing_config (
  tax_rate numeric NOT NULL,
  shipping_flat numeric NOT NULL,
  shipping_threshold numeric NOT NULL,
  currency text NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  tax_enabled boolean NOT NULL DEFAULT true,
  shipping_enabled boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT pricing_config_pkey PRIMARY KEY (id)
);
CREATE TABLE public.system_settings (
  key text NOT NULL,
  category text NOT NULL CHECK (category = ANY (ARRAY['general'::text, 'financial'::text, 'feature_flag'::text, 'operational'::text, 'ui_ux'::text])),
  data_type text NOT NULL CHECK (data_type = ANY (ARRAY['boolean'::text, 'integer'::text, 'decimal'::text, 'string'::text, 'json'::text])),
  value jsonb NOT NULL,
  default_value jsonb NOT NULL,
  description text,
  is_system_locked boolean NOT NULL DEFAULT false,
  is_public boolean NOT NULL DEFAULT false,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT system_settings_pkey PRIMARY KEY (key)
);
CREATE TABLE public.stripe_webhook_events (
  event_id text NOT NULL,
  event_type text NOT NULL,
  payment_intent_id text,
  received_at timestamp with time zone NOT NULL DEFAULT now(),
  processed_at timestamp with time zone,
  CONSTRAINT stripe_webhook_events_pkey PRIMARY KEY (event_id)
);
CREATE TABLE public.payments (
  order_id uuid,
  user_id uuid,
  stripe_payment_intent_id text UNIQUE,
  amount numeric NOT NULL CHECK (amount >= 0::numeric),
  amount_paise bigint,
  payment_method text,
  error_code text,
  error_message text,
  failure_reason text,
  failure_code text,
  attempt_number integer,
  latest_attempt_number integer,
  successful_attempt_number integer,
  latest_payment_intent_id text,
  ip_address text,
  user_agent text,
  first_attempt_at timestamp with time zone,
  last_attempt_at timestamp with time zone,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  currency text NOT NULL DEFAULT 'INR'::text,
  status text NOT NULL DEFAULT 'requires_payment_method'::text,
  total_attempts integer NOT NULL DEFAULT 1,
  gateway_metadata jsonb DEFAULT '{}'::jsonb,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  CONSTRAINT payments_pkey PRIMARY KEY (id),
  CONSTRAINT payments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id),
  CONSTRAINT payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id)
);
CREATE TABLE public.payment_attempts (
  payment_id uuid NOT NULL,
  order_id uuid,
  user_id uuid,
  stripe_payment_intent_id text,
  created_at timestamp with time zone DEFAULT now(),
  attempt_number integer,
  status text NOT NULL,
  amount numeric NOT NULL,
  amount_paise bigint,
  currency text NOT NULL,
  error_message text,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  CONSTRAINT payment_attempts_pkey PRIMARY KEY (id),
  CONSTRAINT payment_attempts_payment_id_fkey FOREIGN KEY (payment_id) REFERENCES public.payments(id)
);